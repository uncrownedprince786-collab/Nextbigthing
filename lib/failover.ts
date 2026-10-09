import pg from "pg";

/// Read failover between two Postgres endpoints, decided at the moment a connection is made.
///
/// **What it is, and the three things it is deliberately not.**
///
/// It is a `pg.Pool` that tries the primary and, when the primary cannot be reached, hands out a
/// connection to a standby instead. It sits under Prisma, through the adapter, so every query the
/// site makes -- including the raw lateral read -- goes through it without a line of query code
/// knowing.
///
///   * **Not a replica.** Two Neon projects do not replicate. The standby holds whatever
///     `jobs/mirror.py` last copied into it, so it can be hours behind. Every page prints the date
///     its prices are as of, which is the only thing standing between "serving the standby" and
///     "serving stale numbers as current" -- and is why this logs every switch.
///   * **Not for writes.** The only writer is the nightly lanes, which connect to the primary
///     directly and never through this. Letting a lane fail over would put two databases in the
///     position of both being written to, and nothing here resolves that.
///   * **Not mid-transaction.** It acts only while a connection is being *established*. A query that
///     fails after connecting is a query error and is raised unchanged: retrying half of a
///     transaction on a different database is how rows end up in neither.
///
/// It is also off unless a fallback connection string is configured (`lib/db.ts` is the one place the
/// environment is read), so merging this changes nothing for a
/// deployment that has not opted in.

/// Failures that mean "this endpoint cannot be used right now", as opposed to "this request was
/// wrong". Only the first kind may switch the standby on.
///
/// Deliberately not on the list: authentication failures (`28xxx`). A wrong password on the primary
/// is a configuration fault that must be loud, and a standby that quietly absorbs it would let a
/// broken credential run in production for as long as the standby held out.
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
  // resources -- which is where Neon's quota lands (`53000`) -- and 57P01..57P03 are the server
  // shutting down or not yet accepting connections.
  if (/^08/.test(code) || /^53/.test(code) || ["57P01", "57P02", "57P03"].includes(code)) return true;
  // The same conditions when the driver wraps them and the code is gone.
  if (
    /exceeded the quota|timeout exceeded when trying to connect|connection terminated|connection timeout|the database system is (starting up|shutting down)/i.test(
      message,
    )
  ) {
    return true;
  }
  return e.cause ? isConnectionFailure(e.cause) : false;
}

/// How long the primary is left alone after it fails, in milliseconds.
///
/// Without it every request pays the primary's connect timeout before reaching the standby, which
/// turns "the primary is down" into "every page takes ten seconds". With it the first request pays
/// once and the rest go straight to the standby, and after the window one request tries the primary
/// again -- so a recovery is noticed within a minute and a single slow request is the whole cost.
export const PRIMARY_COOLDOWN_MS = 60_000;

export interface Connectable<C> {
  connect(): Promise<C>;
}

/// The routing decision, separated from `pg` so it can be tested with a fake endpoint and a clock.
export class Failover<C> {
  private downSince = 0;
  private announced = false;
  private readonly primary: Connectable<C>;
  private readonly standby: Connectable<C> | null;
  private readonly now: () => number;
  private readonly log: (message: string) => void;

  // Explicit fields and not parameter properties: Node's TypeScript stripping, which runs this
  // file under `node --test`, does not support the parameter-property shorthand.
  constructor(
    primary: Connectable<C>,
    standby: Connectable<C> | null,
    now: () => number = Date.now,
    log: (message: string) => void = (m) => console.warn(m),
  ) {
    this.primary = primary;
    this.standby = standby;
    this.now = now;
    this.log = log;
  }

  /// True while the primary is being skipped.
  get usingStandby(): boolean {
    return this.downSince !== 0 && this.now() - this.downSince < PRIMARY_COOLDOWN_MS;
  }

  async connect(): Promise<C> {
    if (this.standby === null) return this.primary.connect();

    if (!this.usingStandby) {
      try {
        const client = await this.primary.connect();
        if (this.downSince !== 0) {
          this.log("failover: the primary database is answering again, so reads have returned to it");
        }
        this.downSince = 0;
        this.announced = false;
        return client;
      } catch (error) {
        // Only a connection-class failure may switch the standby on. Anything else is raised
        // unchanged, so a bad credential or a bad request is never absorbed.
        if (!isConnectionFailure(error)) throw error;
        this.downSince = this.now();
        if (!this.announced) {
          this.announced = true;
          const why = error instanceof Error ? error.message.split("\n")[0].slice(0, 120) : "unknown";
          this.log(
            `failover: the primary database could not be reached (${why}). Reads are being served ` +
              "from the standby, which may be behind. Pages print the date their figures are as of.",
          );
        }
      }
    }
    return this.standby.connect();
  }
}

/// A pool for Prisma's pg adapter that fails over at connection time.
///
/// `pg.Pool.query` is implemented on top of `connect`, and the adapter reaches the pool only through
/// those two, so overriding `connect` is the whole of it. Both call shapes are kept: Prisma uses the
/// promise form and `pg` itself uses the callback form internally.
export function makeFailoverPool(
  primary: pg.PoolConfig,
  standby: pg.PoolConfig | null,
): pg.Pool {
  if (standby === null) return new pg.Pool(primary);

  const standbyPool = new pg.Pool(standby);
  const router: { current: Failover<pg.PoolClient> | null } = { current: null };

  class FailoverPool extends pg.Pool {
    // pg types `connect` as three overloads; the override has to serve all of them.
    // @ts-expect-error -- overload set widened on purpose, see above
    connect(callback?: (err: Error | undefined, client?: pg.PoolClient, done?: (release?: boolean | Error) => void) => void) {
      const route = (router.current ??= new Failover<pg.PoolClient>(
        { connect: () => super.connect() as Promise<pg.PoolClient> },
        { connect: () => standbyPool.connect() },
      ));
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
  return new FailoverPool(primary) as unknown as pg.Pool;
}
