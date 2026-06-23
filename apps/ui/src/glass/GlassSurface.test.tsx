import { render, screen } from "@testing-library/react";
import { GlassSurface } from "./GlassSurface";

test("renders children inside a glass surface", () => {
  render(
    <GlassSurface variant="capsule">
      <span>hello</span>
    </GlassSurface>,
  );
  expect(screen.getByText("hello")).toBeDefined();
  expect(document.querySelector(".glass--capsule")).not.toBeNull();
});
