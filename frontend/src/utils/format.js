// Бэкенд присылает даты строками YYYY-MM-DD. Разбираем их вручную, а не
// через new Date('2026-10-21'): такая запись считается временем в UTC, и в
// часовых поясах западнее Гринвича дата «съехала» бы на день назад.
function parseIsoDate(iso) {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

// Для кнопки с датой: «пн» и «21 окт.».
export function formatDateParts(iso) {
  const date = parseIsoDate(iso)

  return {
    weekday: date.toLocaleDateString('ru-RU', { weekday: 'short' }),
    day: date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
  }
}

// Для текста: «понедельник, 21 октября».
export function formatDateLong(iso) {
  return parseIsoDate(iso).toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
}

// Части дня для списка времени: длинный ряд кнопок проще просматривать
// группами. Границы: утро до 12:00, день до 17:00, дальше вечер.
const DAY_PARTS = [
  { key: 'morning', title: 'Утро', from: 0, to: 12 },
  { key: 'day', title: 'День', from: 12, to: 17 },
  { key: 'evening', title: 'Вечер', from: 17, to: 24 },
]

// ['10:00', '13:30', '18:00'] -> [{key, title, times}, ...] без пустых частей.
export function groupByDayPart(times) {
  return DAY_PARTS.map((part) => ({
    key: part.key,
    title: part.title,
    times: times.filter((time) => {
      const hour = Number(time.slice(0, 2))
      return hour >= part.from && hour < part.to
    }),
  })).filter((part) => part.times.length > 0)
}
