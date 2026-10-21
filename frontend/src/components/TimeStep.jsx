import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatDateLong, groupByDayPart } from '../utils/format'

// Ключ, по которому узнаём, для какой услуги и даты получен ответ.
function makeKey(slug, date) {
  return `${slug}|${date}`
}

// Шаг 3: выбор времени. Показывает свободное время на выбранную дату
// (у любого мастера, оказывающего услугу), разбитое по частям дня.
export default function TimeStep({ service, date, selectedTime, onSelect }) {
  // Ответ хранится вместе с ключом запроса. Пока ключ не совпал с текущим
  // выбором, считаем, что идёт загрузка (тот же приём, что в DateStep).
  const [result, setResult] = useState({ key: null, times: [], failed: false })

  useEffect(() => {
    let cancelled = false
    const key = makeKey(service.slug, date)

    api
      .getTimes(service.slug, date)
      .then((times) => {
        if (!cancelled) setResult({ key, times, failed: false })
      })
      .catch(() => {
        if (!cancelled) setResult({ key, times: [], failed: true })
      })

    return () => {
      cancelled = true
    }
  }, [service.slug, date])

  const loading = result.key !== makeKey(service.slug, date)
  const groups = groupByDayPart(result.times)

  return (
    <section className="step-block">
      <h2 className="step__title">Выберите время</h2>
      <p className="step__hint">{formatDateLong(date)}</p>

      {loading && <p className="note">Ищем свободное время…</p>}

      {!loading && result.failed && (
        <p className="note note--error">
          Не удалось загрузить время. Попробуйте выбрать дату ещё раз.
        </p>
      )}

      {!loading && !result.failed && result.times.length === 0 && (
        <p className="note">
          На эту дату свободного времени не осталось. Выберите другую.
        </p>
      )}

      {groups.map((group) => (
        <div key={group.key} className="day-part">
          <h3 className="day-part__title">{group.title}</h3>
          <ul className="times">
            {group.times.map((time) => (
              <li key={time}>
                <button
                  type="button"
                  className={time === selectedTime ? 'time time--active' : 'time'}
                  aria-pressed={time === selectedTime}
                  onClick={() => onSelect(time)}
                >
                  {time}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {selectedTime && (
        <p className="note">
          Выбрано: {formatDateLong(date)}, {selectedTime}
        </p>
      )}
    </section>
  )
}
