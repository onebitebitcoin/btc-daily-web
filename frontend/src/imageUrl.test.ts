import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cardImageSrc,
  imageVersion,
  isRemoteImage,
  preferredImageWidth,
} from "./imageUrl";

const bundled = { "fed-macro": "/assets/fed-macro-abc123.jpg" };

function stubSaveData(saveData: boolean) {
  vi.stubGlobal("navigator", {
    ...globalThis.navigator,
    connection: { saveData },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("isRemoteImage", () => {
  it.each([
    ["https://cdn.example/a.jpg", true],
    ["http://cdn.example/a.jpg", true],
    ["fed-macro", false],
    [null, false],
    [undefined, false],
  ])("%s -> %s", (input, expected) => {
    expect(isRemoteImage(input as string | null | undefined)).toBe(expected);
  });
});

describe("preferredImageWidth", () => {
  it("defaults to 800", () => {
    expect(preferredImageWidth()).toBe(800);
  });

  it("drops to 480 under Save-Data", () => {
    stubSaveData(true);

    expect(preferredImageWidth()).toBe(480);
  });
});

describe("cardImageSrc", () => {
  it("routes remote CDN images through the resizing proxy", () => {
    const src = cardImageSrc(
      "2026-08-04",
      3,
      "https://cdn.example/huge.jpg",
      bundled,
    );

    expect(src).toBe(
      `/api/img/2026-08-04/3?w=800&v=${imageVersion("https://cdn.example/huge.jpg")}`,
    );
  });

  it("changes the proxy URL when the source image is swapped on republish", () => {
    const before = cardImageSrc(
      "2026-09-27",
      10,
      "https://i.ytimg.com/vi/old/hqdefault.jpg",
      bundled,
    );
    const after = cardImageSrc(
      "2026-09-27",
      10,
      "https://live.staticflickr.com/new.jpg",
      bundled,
    );

    expect(after).not.toBe(before);
  });

  it("keeps the proxy URL stable for the same source image", () => {
    const image = "https://cdn.example/huge.jpg";

    expect(cardImageSrc("2026-08-04", 3, image, bundled)).toBe(
      cardImageSrc("2026-08-04", 3, image, bundled),
    );
  });

  it("asks the proxy for a narrower image under Save-Data", () => {
    stubSaveData(true);

    expect(
      cardImageSrc("2026-08-04", 3, "https://cdn.example/huge.jpg", bundled),
    ).toBe(
      `/api/img/2026-08-04/3?w=480&v=${imageVersion("https://cdn.example/huge.jpg")}`,
    );
  });

  it("uses the bundled asset for a seed stem", () => {
    expect(cardImageSrc("2026-08-04", 1, "fed-macro", bundled)).toBe(
      "/assets/fed-macro-abc123.jpg",
    );
  });

  it("returns undefined for a missing image", () => {
    expect(cardImageSrc("2026-08-04", 8, null, bundled)).toBeUndefined();
  });

  it("returns undefined for an unknown stem rather than a broken path", () => {
    expect(
      cardImageSrc("2026-08-04", 8, "not-bundled", bundled),
    ).toBeUndefined();
  });
});
