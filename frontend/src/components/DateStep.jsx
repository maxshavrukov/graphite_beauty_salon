import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatDateLong, formatDateParts } from '../utils/format'

// Шаг 2: выбор даты. Показывает только те дни, где у любого мастера
// есть свободное время на эту услугу (считает бэкенд).
export default function DateStep({ service, selectedDate, onSelect, onBack }) {
  // Ответ хранится вместе с услугой, для которой он получен. Пока slug не
  // совпал с текущим, считаем, что идёт загрузка: так не нужно сбрасывать
  // состояние внутри эффекта.
  const [result, setResult] = useState({ slug: null, dates: [], failed: false })

  useEffect(() => {
    let cancelled = false

    api
      .getDates(service.slug)
      .then((dates) => {
        if (!cancelled) setResult({ slug: service.slug, dates, failed: false })
      })
      .catch(() => {
        if (!cancelled) setResult({ slug: service.slug, dates: [], failed: true })
      })

    return () => {
      cancelled = true
    }
  }, [service.slug])

  const loading = result.slug !== service.slug

  return (
    <section>
      <button type="button" className="back" onClick={onBack}>
        ← Все услуги
      </button>

      <h2 className="step__title">{service.name}</h2>
      <p className="step__hint">Выберите дату</p>

      {loading && <p className="note">Ищем свободные дни…</p>}

      {!loading && result.failed && (
        <p className="note note--error">
          Не удалось загрузить даты. Попробуйте обновить страницу.
        </p>
      )}

      {!loading && !result.failed && result.dates.length === 0 && (
        <p className="note">
          На ближайшие две недели свободных дат нет. Загляните позже.
        </p>
      )}

      <ul className="dates">
        {result.dates.map((iso) => {
          const { weekday, day } = formatDateParts(iso)

          return (
            <li key={iso}>
              <button
                type="button"
                className={iso === selectedDate ? 'date date--active' : 'date'}
                aria-pressed={iso === selectedDate}
                onClick={() => onSelect(iso)}
              >
                <span className="date__weekday">{weekday}</span>
                <span className="date__day">{day}</span>
              </button>
            </li>
          )
        })}
      </ul>

      {selectedDate && (
        <p className="note">Выбрана дата: {formatDateLong(selectedDate)}</p>
      )}
    </section>
  )
}
