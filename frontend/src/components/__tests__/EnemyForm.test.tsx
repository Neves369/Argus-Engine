import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import EnemyForm from '../EnemyForm'

describe('EnemyForm', () => {
  const base = { name: '', url: '', notes: '' }

  it('salva os campos preenchidos', () => {
    const onSave = vi.fn()
    render(<EnemyForm value={base} onSave={onSave} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Nome'), {
      target: { value: 'exemplo.com' },
    })
    fireEvent.change(screen.getByLabelText('URL'), {
      target: { value: 'https://exemplo.com:4280/' },
    })
    fireEvent.click(screen.getByText('Salvar'))

    expect(onSave).toHaveBeenCalledWith({
      name: 'exemplo.com',
      url: 'https://exemplo.com:4280/',
      notes: '',
    })
  })

  it('alerta quando o Nome contém uma porta', () => {
    render(<EnemyForm value={base} onSave={vi.fn()} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Nome'), {
      target: { value: 'exemplo.com:4280' },
    })

    expect(
      screen.getByText(/A porta deve ir no campo URL/),
    ).toBeInTheDocument()
  })

  it('não alerta para Nome sem porta', () => {
    render(<EnemyForm value={base} onSave={vi.fn()} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('Nome'), {
      target: { value: 'exemplo.com' },
    })

    expect(screen.queryByText(/A porta deve ir no campo URL/)).not.toBeInTheDocument()
  })
})