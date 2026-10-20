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
