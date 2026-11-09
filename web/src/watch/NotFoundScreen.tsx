// A path the app has no page for, such as an old bookmark: it says so, with the way home.
import { Link, useLocation } from 'react-router'
import { Nothing } from './Shown'

export function NotFoundScreen() {
  const { pathname } = useLocation()
  return (
    <>
      <h1 className="sr-only">No such page</h1>
      <Nothing title={`There is nothing at ${pathname}`}>The link may be from an older version of the app. <Link to="/" className="text-tube-focus">Go home</Link>.</Nothing>
    </>
  )
}
