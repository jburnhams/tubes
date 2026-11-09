import type { Meta, StoryObj } from '@storybook/react-vite'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Not found',
  render: () => <AppAt route="/an/old/bookmark" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const NoSuchPage: Story = {}
