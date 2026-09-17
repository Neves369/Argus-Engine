import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import Hand from '../Hand'

describe('Hand', () => {
  it('mostra a mão completa quando o tabuleiro está vazio', () => {
    const { container } = render(<Hand palette />)
    expect(container.querySelectorAll('.hand-card')).toHaveLength(5)
  })

  it('esconde da mão qualquer carta que esteja no tabuleiro', () => {
    const { container } = render(<Hand palette playedCards={[0, 1, 4, 3]} />)
    expect(container.querySelectorAll('.hand-card')).toHaveLength(1)
  })

  it('nunca exibe uma carta na mão e no tabuleiro ao mesmo tempo', () => {
    const { container } = render(<Hand palette playedCards={[2]} />)
    expect(container.querySelectorAll('.hand-card')).toHaveLength(4)
  })

  it('esconde a mão inteira quando hidden', () => {
    const { container } = render(<Hand palette hidden />)
    const hand = container.querySelector('.hand')
    expect(hand).toHaveClass('is-hidden')
    expect(hand?.querySelectorAll('.hand-card')).toHaveLength(5)
  })

  it('dá aura de chamas à carta do Carro em Modo Death', () => {
    const { container } = render(<Hand palette deathMode />)
    const chariot = Array.from(container.querySelectorAll('.hand-card'))[2]
    expect(chariot).toHaveClass('is-death-aura')
    expect(chariot?.querySelectorAll('.particle--flame-loop')).toHaveLength(14)
  })

  it('não dá aura de chamas à carta do Carro fora do Modo Death', () => {
    const { container } = render(<Hand palette />)
    expect(container.querySelector('.is-death-aura')).toBeNull()
  })
})