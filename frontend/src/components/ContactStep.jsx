import { useState } from 'react'
import { api } from '../api/client'
import { describeBookingError } from '../utils/bookingErrors'
import { cleanPhoneInput, isValidPhone, toApiPhone } from '../utils/phone'
import BookingSummary from './BookingSummary'

const NO_ERRORS = { general: null, name: null, phone: null }

// Шаг 5: имя и телефон, отправка заявки. Введённые имя и телефон хранит
// App (contact), чтобы они не пропадали, если клиент вернётся и сменит время.
export default function ContactStep({
  service,
  date,
  time,
  selected,
  contact,
  onChange,
  onSuccess,
  onConflict,
}) {
  const [sending, setSending] = useState(false)
  const [errors, setErrors] = useState(NO_ERRORS)

  function update(field, value) {
    onChange({ ...contact, [field]: value })
    // Клиент исправляет поле: старую ошибку про него больше не показываем.
    setErrors((previous) => ({ ...previous, [field]: null, general: null }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (sending) return

    // Быстрая проверка до отправки; окончательную делает сервер.
    const name = contact.name.trim()
    const fieldErrors = {
      name: name ? null : 'Укажите имя.',
      phone: isValidPhone(contact.phone)
        ? null
        : 'Введите номер в формате 0991234567.',
    }

    if (fieldErrors.name || fieldErrors.phone) {
      setErrors({ general: null, ...fieldErrors })
      return
    }

    setSending(true)
    setErrors(NO_ERRORS)

    try {
      const result = await api.createBooking({
        master: selected.master.slug,
        service: service.slug,
        date,
        start_time: time,
        client_name: name,
        client_phone: toApiPhone(contact.phone),
      })

      onSuccess(result)
    } catch (error) {
      const problem = describeBookingError(error)

      setSending(false)

      if (problem.resetTime) {
        // Время больше не подходит: App сбросит выбор и покажет причину
        // над списком времени, эта форма при этом исчезнет.
        onConflict(problem.general)
        return
      }

      setErrors({
        general: problem.general ?? null,
        name: problem.fields?.name ?? null,
        phone: problem.fields?.phone ?? null,
      })
    }
  }

  return (
    <section className="step-block">
      <h2 className="step__title">Ваши контакты</h2>

      <BookingSummary
        service={service}
        date={date}
        time={time}
        selected={selected}
      />

      <form className="form" onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label className="field__label" htmlFor="client-name">
            Имя
          </label>
          <input
            id="client-name"
            className={errors.name ? 'input input--invalid' : 'input'}
            type="text"
            name="name"
            autoComplete="name"
            maxLength={100}
            placeholder="Как к вам обращаться"
            value={contact.name}
            onChange={(event) => update('name', event.target.value)}
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? 'client-name-error' : undefined}
          />
          {errors.name && (
            <p id="client-name-error" className="field__error">
              {errors.name}
            </p>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="client-phone">
            Телефон
          </label>
          <div className={errors.phone ? 'phone phone--invalid' : 'phone'}>
            <span className="phone__prefix">+38</span>
            <input
              id="client-phone"
              className="phone__input"
              type="tel"
              name="phone"
              inputMode="tel"
              autoComplete="tel-national"
              placeholder="099 123 45 67"
              value={contact.phone}
              onChange={(event) =>
                update('phone', cleanPhoneInput(event.target.value))
              }
              aria-invalid={Boolean(errors.phone)}
              aria-describedby={errors.phone ? 'client-phone-error' : undefined}
            />
          </div>
          {errors.phone && (
            <p id="client-phone-error" className="field__error">
              {errors.phone}
            </p>
          )}
        </div>

        {errors.general && <p className="note note--error">{errors.general}</p>}

        <p className="form__hint">
          После отправки администратор перезвонит вам и подтвердит запись.
        </p>

        <button type="submit" className="button" disabled={sending}>
          {sending ? 'Отправляем…' : 'Записаться'}
        </button>
      </form>
    </section>
  )
}
