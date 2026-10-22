// Holiday F-187: react-router-dom 6.26 prints a future-flag notice on every
// router mount until both v7 flags are set. `v7_startTransition` only wraps
// navigations in startTransition, and `v7_relativeSplatPath` changes how a
// relative link resolves under a `*` route, which no hub or App.tsx declares
// (the one `path="*"` is a test fixture in hubs/taburl.test.tsx). The app's
// BrowserRouter and every test's MemoryRouter spread this one constant, so the
// two cannot drift and a test runs under the router the app runs under.
export const routerFuture = {
  future: { v7_startTransition: true, v7_relativeSplatPath: true },
} as const
