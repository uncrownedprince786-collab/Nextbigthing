import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ClassIndex } from "@/components/classIndex";
import { classBySlug } from "@/lib/assetClass";

/// The crypto index.
///
/// A four line route on purpose. Everything that renders is in `ClassIndex`, and everything that
/// differs between the four classes is data in `ASSET_CLASSES` -- which is what keeps `/crypto`
/// from quietly sorting differently to `/stocks` after someone fixes one of them.
///
/// Its own path rather than a `[slug]` segment, because these four are the site's top level
/// browse and a reader is meant to be able to type them. A dynamic segment would also accept
/// `/anything` and have to 404 it at render time, after the queries had already run.
export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Crypto",
  description:
    "Every coin the site covers, with one reading each.",
};

export default function Page() {
  const cls = classBySlug("crypto");
  // Unreachable while ASSET_CLASSES holds this slug, and a 404 rather than a throw if it ever
  // stops: a missing class is a page that does not exist, not a server fault.
  if (!cls) notFound();
  return <ClassIndex cls={cls} />;
}
