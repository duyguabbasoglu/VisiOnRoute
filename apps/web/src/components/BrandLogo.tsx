import Image from "next/image";
import icon from "../../public/brand/visionroute-icon.png";
import wordmark from "../../public/brand/visionroute-wordmark-trimmed.png";

/**
 * The official VisiOnRoute logo (public/brand/). The artwork is used as
 * supplied: never recolored, redrawn or stretched; only its height is set and
 * the width follows the intrinsic aspect ratio. The logo is dark navy, so on
 * dark surfaces pass `plate` to seat it on a small white container instead of
 * altering its colors.
 *
 * - "wordmark": emblem + name, wherever horizontal space allows.
 * - "icon": the shield emblem alone (a pixel-exact crop of the wordmark) for
 *   compact and mobile contexts.
 * - "responsive": icon on very narrow screens, wordmark from 400px up.
 */
type Variant = "wordmark" | "icon" | "responsive";

const HEIGHTS = {
  sm: "h-7",
  md: "h-8",
  lg: "h-10",
} as const;

export function BrandLogo({
  variant = "wordmark",
  size = "md",
  plate = false,
  priority = false,
  className = "",
}: {
  variant?: Variant;
  size?: keyof typeof HEIGHTS;
  plate?: boolean;
  priority?: boolean;
  className?: string;
}) {
  const height = HEIGHTS[size];
  const image = (src: typeof wordmark, extra = "") => (
    <Image
      src={src}
      alt="VisiOnRoute"
      priority={priority}
      className={`${height} w-auto max-w-none select-none ${extra}`}
      draggable={false}
    />
  );
  const content =
    variant === "responsive" ? (
      <>
        {image(icon, "min-[400px]:hidden")}
        {image(wordmark, "hidden min-[400px]:block")}
      </>
    ) : (
      image(variant === "icon" ? icon : wordmark)
    );
  return (
    <span
      className={`inline-flex shrink-0 items-center ${
        plate ? "rounded-lg bg-white px-2 py-1 shadow-sm ring-1 ring-black/5" : ""
      } ${className}`}
    >
      {content}
    </span>
  );
}
