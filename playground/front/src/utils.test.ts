import { expect, it } from "vitest";
import { tranformHankakuToZenkaku } from "./utils";

it("tranformHankakuToZenkaku", () => {
  const testCases = [
    { input: "abc", expected: "ａｂｃ" },
    { input: "123", expected: "１２３" },
    { input: "9", expected: "９" },
    { input: "あいう", expected: "あいう" },
    { input: "５", expected: "５" },
  ];

  testCases.forEach((tc) =>
    expect(tranformHankakuToZenkaku(tc.input)).toEqual(tc.expected)
  );
});
