import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatDateLong, formatPrice } from '../utils/format'

// Ключ, по которому узнаём, для какого выбора получен ответ.
function makeKey(slug, date, time) {
  return `${slug}|${date}|${time}`
}

// Шаг 4: выбор мастера. Показывает мастеров, свободных именно в это время,
// и цену у каждого: цены у мастеров на одну услугу могут отличаться.
export default function MasterStep({ service, date, time, selected, onSelect }) {
  // Ответ хранится вместе с ключом запроса (тот же приём, что в DateStep).
  const [result, setResult] = useState({ key: null, items: [], failed: false })

  useEffect(() => {
    let cancelled = false
    const key = makeKey(service.slug, date, time)

    api
      .getMastersForSlot(service.slug, date, time)
      .then((items) => {
        if (!cancelled) setResult({ key, items, failed: false })
      })
      .catch(() => {
        if (!cancelled) setResult({ key, items: [], failed: true })
      })

    return () => {
      cancelled = true
    }
  }, [service.slug, date, time])

  const loading = result.key !== makeKey(service.slug, date, time)

  return (
    <section className="step-block">
      <h2 className="step__title">Выберите мастера</h2>
      <p className="step__hint">
        {formatDateLong(date)}, {time}
      </p>

      {loading && <p className="note">Ищем свободных мастеров…</p>}

      {!loading && result.failed && (
        <p className="note note--error">
          Не удалось загрузить мастеров. Попробуйте выбрать время ещё раз.
        </p>
      )}

      {!loading && !result.failed && result.items.length === 0 && (
        <p className="note">
          На это время свободных мастеров не осталось. Выберите другое время.
        </p>
      )}

      <ul className="masters">
        {result.items.map(({ master, price }) => {
          const isSelected = selected?.master.slug === master.slug

          return (
            <li key={master.slug}>
              <button
                type="button"
                className={isSelected ? 'master master--active' : 'master'}
                aria-pressed={isSelected}
                onClick={() => onSelect({ master, price })}
              >
                {master.photo ? (
                  <img className="avatar" src={master.photo} alt="" />
                ) : (
                  <span className="avatar avatar--empty">
                    {master.name.charAt(0)}
                  </span>
                )}

                <span className="master__info">
                  <strong>{master.name}</strong>
                  {master.bio && (
                    <span className="master__bio">{master.bio}</span>
                  )}
                </span>

                <span className="master__price">{formatPrice(price)}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
