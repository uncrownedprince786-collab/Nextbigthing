import pg from "pg";

/// Read failover across an ordered list of Postgres endpoints, decided when a connection is made.
///
/// **What it is, and the three things it is deliberately not.**
///
/// A `pg.Pool` that tries its endpoints in strict priority order -- the primary, then each standby in
/// the order given -- and hands out a connection to the first one that can be used. It sits under
/// Prisma, through the adapter, so every query the site makes, including the raw lateral read, goes
/// through it without a line of query code knowing.
///
///   * **Not a replica.** Separate Postgres projects do not replicate. A standby holds whatever
///     `jobs/mirror.py` last copied into it, so it can be hours behind. Every page prints the date
///     its prices are as of, and the rule table refuses a stale close at gate 2, which is what stands
///     between "serving a standby" and "serving stale numbers as current" -- and why every switch is
///     logged.
///   * **Not for writes.** The writers are the lanes, which do not go through this pool. Since
///     2026-10-10 they fail over on their own (jobs/nbt.py `db`, tools/writer.mjs): when the primary
///     cannot be reached they write the standby, and jobs/reconcile.py copies those rows back the first
///     time a lane reaches the primary again -- which is what makes two written databases safe.
///   * **Not mid-transaction.** It acts only while a connection is being *established*. A query that
///     fails after connecting is a query error and is raised unchanged: retrying half a transaction
///     on a different database is how rows end up in neither.
///
/// It is also off unless a standby is configured (`lib/db.ts` is the one place the environment is
/// read), so merging this changes nothing for a deployment that has not opted in.

/// Failures that mean "this endpoint cannot be used right now", as opposed to "this request was
/// wrong". Only the first kind may move on to the next tier.
///
/// Deliberately not on the list: authentication failures (`28xxx`). A wrong password is a
/// configuration fault, and absorbing it would let a broken credential run for as long as another
/// tier held out. (A *standby's* bad credential is handled apart, in `Failover.connect`: loud, and the
/// tier is skipped, but never at the cost of the request.)
export function isConnectionFailure(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const e = error as { code?: unknown; message?: unknown; cause?: unknown };
  const code = typeof e.code === "string" ? e.code : "";
  const message = typeof e.message === "string" ? e.message : "";

  // Network level: the endpoint did not answer, or was not found, or hung up.
  if (
    [
      "ECONNREFUSED",
      "ECONNRESET",
      "ETIMEDOUT",
      "ENOTFOUND",
      "EAI_AGAIN",
      "EHOSTUNREACH",
      "ENETUNREACH",
      "EPIPE",
    ].includes(code)
  ) {
    return true;
  }
  // Postgres level, raised during startup. Class 08 is a connection exception, 53 is insufficient
  // resources -- Neon's quota lands there (`53000`), and so does a pooler with no free slot
  // (`53300`, "too many clients") -- and 57P01..57P03 are the server shutting down or not yet
  // accepting connections.
  //
  // A full pooler is the case that is easy to miss, because it does not always arrive as class 53:
  // Supabase's session pooler answers `XX000` with "(EMAXCONNSESSION) max clients reached" once its
  // 15 slots are taken. That is capacity exhaustion, the same condition as `53300`, and treating it as
  // a configuration fault made a full standby fail the request instead of being skipped.
  if (/^08/.test(code) || /^53/.test(code) || ["57P01", "57P02", "57P03"].includes(code)) return true;
  // The same conditions as Prisma reports them to a query, which is the shape a page sees (the pool
  // sees pg's): P1001 cannot reach the server, P1002 timed out reaching it, P1017 the server closed the
  // connection. Found by a build run with every tier unreachable: the page's error was P1001 with the
  // driver's own error tucked in `meta.driverAdapterError`, and nothing above recognised it.
  if (["P1001", "P1002", "P1017"].includes(code)) return true;
  // The same conditions when the driver wraps them and the code is gone.
  if (
    /exceeded the quota|timeout exceeded when trying to connect|connection terminated|connection timeout|the database system is (starting up|shutting down)|too many clients|remaining connection slots|max clients reached|EMAXCONN|can't reach database server|DatabaseNotReachable/i.test(
      message,
    )
  ) {
    return true;
  }
  const adapter = (e as { meta?: { driverAdapterError?: unknown } }).meta?.driverAdapterError;
  if (adapter && isConnectionFailure(adapter)) return true;
  return e.cause ? isConnectionFailure(e.cause) : false;
}

/// How long an endpoint is left alone after it fails, in milliseconds.
///
/// Without it every request pays a dead endpoint's connect timeout before reaching one that works,
/// which turns "the primary is down" into "every page takes five seconds". With it the first request
/// pays once and the rest go straight to the next tier, and after the window one request tries the
/// failed endpoint again -- so a recovery is noticed within a minute at the cost of one slow request.
/// Kept per endpoint, so a dead standby does not stop a healthy primary being used.
export const COOLDOWN_MS = 60_000;

/// How long a standby that has been checked for data is trusted before it is checked again.
export const VETTING_TTL_MS = 300_000;

/// The longest a connection attempt may take before it counts as a failure, in milliseconds.
///
/// `pg.Pool` defaults to no timeout at all, so a black-holed endpoint -- one that accepts the packet
/// and never answers -- would hang the request forever instead of failing over. Five seconds is
/// longer than a cold Neon wake-up and shorter than a page anyone waits for.
export const CONNECT_TIMEOUT_MS = 5_000;

/// Connections a standby pool may open, per process.
///
/// Small on purpose, and measured rather than guessed: Supabase's free session pooler admits 15
/// clients in total, across everything that connects to it. An earlier ceiling of 5 per process was
/// exhausted by three test servers and a running mirror, and in production every concurrent serverless
/// instance has its own pool, so a handful of instances during an outage would drain it. A standby is
/// idle until needed and serves a degraded site.
///
/// One, since 2026-10-10: during a real failover three per instance filled all 15 slots ("max clients
/// reached in session mode") and the standby turned every request away, primary already gone. Idle
/// connections are also let go after `STANDBY_IDLE_MS`, because a serverless instance that is frozen
/// between requests otherwise keeps its slot until the platform recycles it.
export const STANDBY_MAX_CLIENTS = 1;
export const STANDBY_IDLE_MS = 2_000;

export interface Tier<C> {
  /// A label for logs. Never a host and never a credential.
  name: string;
  connect(): Promise<C>;
  /// Is this endpoint fit to serve, given a connection to it? Asked of standbys only, and only when
  /// one is first used or every few minutes after.
  accept?(client: C): Promise<boolean>;
  /// Give back a connection that was opened and then rejected.
  discard?(client: C): void;
}

/// The routing decision, separated from `pg` so it can be tested with fake endpoints and a clock.
export class Failover<C> {
  private readonly tiers: Tier<C>[];
  private readonly now: () => number;
  private readonly log: (message: string) => void;
  /// When each tier last failed, by index. Absent means it has not, or has since recovered.
  private readonly downSince = new Map<number, number>();
  /// When each standby last passed its data check.
  private readonly vettedAt = new Map<number, number>();
  /// Which tiers have already been announced as failing, so a continuing outage logs once.
  private readonly announced = new Set<number>();
  private serving = 0;

  // Explicit fields and not parameter properties: Node's TypeScript stripping, which runs this
  // file under `node --test`, does not support the parameter-property shorthand.
  constructor(
    tiers: Tier<C>[],
    now: () => number = Date.now,
    log: (message: string) => void = (m) => console.warn(m),
  ) {
    if (tiers.length === 0) throw new Error("a failover needs at least one endpoint");
    this.tiers = tiers;
    this.now = now;
    this.log = log;
  }

  private inCooldown(index: number): boolean {
    const since = this.downSince.get(index);
    return since !== undefined && this.now() - since < COOLDOWN_MS;
  }

  /// The label of the tier that last served a connection.
  get servingFrom(): string {
    return this.tiers[this.serving].name;
  }

  /// True while the primary is being skipped.
  get usingStandby(): boolean {
    return this.inCooldown(0);
  }

  private markDown(index: number, why: string): void {
    this.downSince.set(index, this.now());
    this.vettedAt.delete(index);
    if (!this.announced.has(index)) {
      this.announced.add(index);
      this.log(`failover: ${this.tiers[index].name} cannot be used (${why}).`);
    }
  }

  async connect(): Promise<C> {
    // Tiers not in cooldown, in priority order. If every one is, try them all anyway in the same
    // order: refusing to try for a minute after the last endpoint failed would turn one recovery
    // into a minute of certain errors.
    const live = this.tiers.map((_, i) => i).filter((i) => !this.inCooldown(i));
    const order = live.length ? live : this.tiers.map((_, i) => i);

    let first: unknown = null;
    for (const i of order) {
      const tier = this.tiers[i];
      let client: C;
      try {
        client = await tier.connect();
      } catch (error) {
        if (isConnectionFailure(error)) {
          first ??= error;
          this.markDown(i, describe(error));
          continue;
        }
        // The primary's own bad request or bad credential is raised unchanged, so a broken
        // configuration is loud. A standby's is not worth failing the request for: say so, loudly
        // and once, skip it, and let the next tier serve.
        if (i === 0) throw error;
        first ??= error;
        this.markDown(i, `${describe(error)} -- this is a configuration fault, not an outage`);
        continue;
      }

      // A standby that answers but holds nothing would serve "0 names" as though it were the site,
      // which is worse than an honest error page. Checked on first use and then every few minutes.
      if (i > 0 && tier.accept && this.now() - (this.vettedAt.get(i) ?? -Infinity) > VETTING_TTL_MS) {
        let fit = false;
        try {
          fit = await tier.accept(client);
        } catch (error) {
          fit = false;
          if (!isConnectionFailure(error)) first ??= error;
        }
        if (!fit) {
          tier.discard?.(client);
          this.markDown(i, "it answered but holds no data");
          continue;
        }
        this.vettedAt.set(i, this.now());
      }

      this.downSince.delete(i);
      this.announced.delete(i);
      if (i !== this.serving) {
        this.log(
          i === 0
            ? `failover: ${tier.name} is answering again, so reads have returned to it.`
            : `failover: reads are being served from ${tier.name}, which may be behind. Pages print the date their figures are as of.`,
        );
        this.serving = i;
      }
      return client;
    }
    // Nothing could be used. The first failure is the one an operator needs: it is the primary's
    // whenever the primary was tried.
    throw first ?? new Error("no database endpoint is available");
  }
}

/// One line about a failure, safe to log.
///
/// A driver's error can carry the whole connection string -- psycopg's "invalid connection option"
/// does, and a live password reached a terminal that way earlier in this project's history -- and
/// this line goes to a server log. So any URL is replaced before the text is shortened, not after.
function describe(error: unknown): string {
  if (!(error instanceof Error)) return "unknown";
  return error.message
    .replace(/postgres(?:ql)?:\/\/\S+/gi, "<redacted-url>")
    .split("\n")[0]
    .slice(0, 120);
}

/// The connection string, with encryption asked for when it did not say.
///
/// Measured against the real Supabase pooler with the Node driver: with no mode at all the driver
/// connects **unencrypted**; `sslmode=require` fails with "self-signed certificate in certificate
/// chain", because node-pg reads `require` as full certificate verification and Supabase's CA is not
/// in Node's store; and `uselibpqcompat=true&sslmode=require` connects encrypted. That last form is
/// libpq's own `require` -- the connection is encrypted, the certificate chain is not verified --
/// which is what the Postgres world means by the word.
///
/// A URL that already names a mode is left exactly as it was, so Neon's `sslmode=require` strings
/// keep their stricter reading, and the tool that wrote them chose it. This is applied on the Node
/// side only: Python's driver rejects `uselibpqcompat` as an unknown connection option.
export function withEncryption(url: string): string {
  if (/[?&]sslmode=/i.test(url)) return url;
  return url + (url.includes("?") ? "&" : "?") + "uselibpqcompat=true&sslmode=require";
}

export interface StandbyConfig {
  name: string;
  config: pg.PoolConfig;
}

/// A pool for Prisma's pg adapter that cascades through the endpoints at connection time.
///
/// `pg.Pool.query` is implemented on top of `connect`, and the adapter reaches the pool only through
/// those two, so overriding `connect` is the whole of it. Both call shapes are kept: Prisma uses the
/// promise form and `pg` itself uses the callback form internally.
export function makeFailoverPool(primary: pg.PoolConfig, standbys: StandbyConfig[]): pg.Pool {
  if (standbys.length === 0) return new pg.Pool(primary);

  // Every pool gets a connect timeout unless one was set: see CONNECT_TIMEOUT_MS. Standbys also get a
  // small ceiling, because they are idle until needed and a free-tier pooler admits few clients.
  const withTimeout = (c: pg.PoolConfig, max?: number): pg.PoolConfig => ({
    connectionTimeoutMillis: CONNECT_TIMEOUT_MS,
    ...(max ? { max, idleTimeoutMillis: STANDBY_IDLE_MS, allowExitOnIdle: true } : {}),
    ...c,
  });
  const standbyPools = standbys.map((s) => ({ name: s.name, pool: new pg.Pool(withTimeout(s.config, STANDBY_MAX_CLIENTS)) }));
  const router: { current: Failover<pg.PoolClient> | null } = { current: null };

  class FailoverPool extends pg.Pool {
    // pg types `connect` as three overloads; the override has to serve all of them.
    // @ts-expect-error -- overload set widened on purpose, see above
    connect(callback?: (err: Error | undefined, client?: pg.PoolClient, done?: (release?: boolean | Error) => void) => void) {
      const route = (router.current ??= new Failover<pg.PoolClient>([
        { name: "the primary", connect: () => super.connect() as Promise<pg.PoolClient> },
        ...standbyPools.map(({ name, pool }) => ({
          name,
          connect: () => pool.connect(),
          // Non-empty is enough. A standby that is merely behind is the rule table's business: its
          // stale-close gate refuses an old price and the page prints the date, so an old copy is
          // honest. An empty one would say "0 names" and be believed.
          accept: async (client: pg.PoolClient) => {
            const { rowCount } = await client.query('SELECT 1 FROM "PriceSnapshot" LIMIT 1');
            return (rowCount ?? 0) > 0;
          },
          discard: (client: pg.PoolClient) => client.release(),
        })),
      ]));
      const promise = route.connect();
      if (typeof callback !== "function") return promise;
      promise.then(
        (client) => callback(undefined, client, client.release.bind(client)),
        (error) => callback(error as Error, undefined, () => {}),
      );
      return undefined;
    }
  }
  // Cast: the override returns `undefined` on the callback path, exactly as `pg`'s own does, which
  // the declared overloads cannot express.
  const pool = new FailoverPool(withTimeout(primary)) as unknown as pg.Pool & { servingFrom?: () => string };
  // Which tier the last connection came from, for the rule that publishes no call from a standby read.
  pool.servingFrom = () => router.current?.servingFrom ?? "the primary";
  return pool;
}
