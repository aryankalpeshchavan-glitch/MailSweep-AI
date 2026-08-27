import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Ensure jsdom / RTL is clean between tests.
afterEach(() => {
  cleanup();
});