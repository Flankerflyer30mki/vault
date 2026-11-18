import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "./api";
import { AuthProvider, useAuth } from "./auth";
import GoogleButton from "./GoogleButton";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal()),
  default: { get: vi.fn(), post: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  delete window.google;
});

// A stand-in for Google Identity Services: records the callback so a test can play Google's part.
function fakeGoogle() {
  const g = { callback: null, initialize: vi.fn(), renderButton: vi.fn() };
  g.initialize.mockImplementation((opts) => {
    g.callback = opts.callback;
  });
  window.google = { accounts: { id: g } };
  return g;
}

function Who() {
  const { user } = useAuth();
  return <p>{user ? `signed in as ${user.email}` : "signed out"}</p>;
}

function renderWith(clientId, onDone) {
  api.get.mockResolvedValue({ data: { user: null, google_client_id: clientId } });
  return render(
    <AuthProvider>
      <GoogleButton onDone={onDone} />
      <Who />
    </AuthProvider>,
  );
}

describe("GoogleButton", () => {
  it("is hidden when the server has no Google client ID", async () => {
    const g = fakeGoogle();
    renderWith("");
    await screen.findByText("signed out");
    expect(screen.queryByTestId("google-button")).toBeNull();
    expect(g.initialize).not.toHaveBeenCalled();
  });

  it("sends Google's credential to the API and signs in", async () => {
    const g = fakeGoogle();
    const onDone = vi.fn();
    api.post.mockResolvedValue({ data: { user: { id: 8, email: "ada@gmail.com" } } });
    renderWith("cid.apps.googleusercontent.com", onDone);
    await waitFor(() => expect(g.initialize).toHaveBeenCalled());
    expect(g.initialize.mock.calls[0][0].client_id).toBe("cid.apps.googleusercontent.com");
    expect(g.renderButton).toHaveBeenCalledWith(screen.getByTestId("google-button"), expect.any(Object));

    g.callback({ credential: "header.payload.signature" });
    await screen.findByText("signed in as ada@gmail.com");
    expect(api.post).toHaveBeenCalledWith("/auth/google/", { credential: "header.payload.signature" });
    expect(onDone).toHaveBeenCalled();
  });

  it("shows the server's error and stays signed out", async () => {
    const g = fakeGoogle();
    api.post.mockRejectedValue({ response: { status: 400, data: { detail: "Google sign-in failed. Please try again." } } });
    renderWith("cid.apps.googleusercontent.com");
    await waitFor(() => expect(g.initialize).toHaveBeenCalled());
    g.callback({ credential: "bad" });
    expect(await screen.findByText(/Google sign-in failed/)).toBeTruthy();
    expect(screen.getByText("signed out")).toBeTruthy();
  });
});
