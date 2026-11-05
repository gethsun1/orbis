import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { App } from './App'

describe('operator console foundation', () => {
  it('shows honest unavailable and empty states without fabricated activity', () => {
    render(<App />)
    expect(screen.getByText('API NOT CONNECTED')).toBeTruthy()
    expect(screen.getByText('No network identity available')).toBeTruthy()
    expect(screen.getByText('No persisted activity returned')).toBeTruthy()
    expect(screen.getByText('No findings returned')).toBeTruthy()
  })
})
