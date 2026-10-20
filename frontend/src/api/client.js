// Все запросы к бэкенду живут здесь. Страницы и компоненты не знают
// ни адресов, ни формата ошибок: они вызывают api.getCategories() и т.п.
//
// В разработке Vite проксирует /api на Django (см. vite.config.js),
// поэтому адреса относительные и CORS не нужен.

async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  let data = null
  try {
    data = await response.json()
  } catch {
    // Пустой или не-JSON ответ: оставляем data = null.
  }

  if (!response.ok) {
    // Бэкенд отдаёт {detail: "..."} (например, 409 «время занято»)
    // или словарь ошибок по полям (400): {client_phone: ["..."]}.
    const error = new Error(data?.detail ?? 'Не удалось выполнить запрос')
    error.status = response.status
    error.fields = response.status === 400 ? data : null
    throw error
  }

  return data
}

function query(params) {
  return `?${new URLSearchParams(params)}`
}

export const api = {
  // Категории со вложенными активными услугами.
  getCategories: () => request('/categories/'),

  // Мастера (для страницы «Наши мастера»).
  getMasters: () => request('/masters/'),

  // «Быстрая запись»: услуга -> дата -> время -> мастер.
  // Даты приходят строками YYYY-MM-DD, время строками HH:MM.
  getDates: (serviceSlug) =>
    request(`/services/${serviceSlug}/available-dates/`),

  getTimes: (serviceSlug, date) =>
    request(`/services/${serviceSlug}/available-times/${query({ date })}`),

  // [{master: {slug, name, photo, bio}, price: "450.00"}, ...]
  getMastersForSlot: (serviceSlug, date, time) =>
    request(
      `/services/${serviceSlug}/available-masters/${query({ date, time })}`,
    ),

  // payload: {master, service, date, start_time, client_name, client_phone}
  // (master и service — slug'и). Ответ 201 содержит status «NEW»,
  // client_name и client_phone в нормализованном виде.
  createBooking: (payload) =>
    request('/bookings/', { method: 'POST', body: JSON.stringify(payload) }),
}
