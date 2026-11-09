// A path the app has no screen for, such as an old bookmark. It says so and offers the way back,
// rather than showing an empty frame.
import { Link, useLocation } from 'react-router'
import { Button, EmptyState, PageHeader } from 'strata-react'

export function NotFoundScreen() {
  const { pathname } = useLocation()
  return (
    <>
      <PageHeader title="No such page" />
      <EmptyState title={`There is nothing at ${pathname}`} action={<Button asChild variant="default"><Link to="/">Browse the library</Link></Button>}>
        The link may be from an older version of the app. Every screen is in the menu.
      </EmptyState>
    </>
  )
}
