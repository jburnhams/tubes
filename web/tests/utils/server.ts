// The one MSW server for the jsdom tests, serving the app's own mock handlers (src/mocks/handlers.ts),
// the same ones Storybook and the visual suite use. Put the server into another state with
// `server.use(messagesError)`; every request needs a handler (setup.ts fails the test otherwise).
import { setupServer } from 'msw/node'
import { handlers } from '../../src/mocks/handlers'

export const server = setupServer(...handlers)
export { mock, resetMock } from '../../src/mocks/handlers'
