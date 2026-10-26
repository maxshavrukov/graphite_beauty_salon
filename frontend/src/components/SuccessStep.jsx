import BookingSummary from './BookingSummary'

// Экран после отправки заявки. Запись ещё не подтверждена: клиенту
// говорим, что администратор перезвонит. Номер берём из ответа сервера,
// то есть в том виде, в каком он сохранён (+380XXXXXXXXX): клиент
// сразу заметит опечатку.
export default function SuccessStep({
  result,
  service,
  date,
  time,
  selected,
  onRestart,
}) {
  return (
    <section className="success">
      <h2 className="step__title">Заявка принята</h2>
      <p className="success__text">
        Мы перезвоним вам на номер {result.client_phone}, чтобы подтвердить
        запись.
      </p>

      <BookingSummary
        service={service}
        date={date}
        time={time}
        selected={selected}
      />

      <p className="form__hint">
        Запись станет окончательной после подтверждения администратором.
      </p>

      <button type="button" className="button" onClick={onRestart}>
        Записаться ещё
      </button>
    </section>
  )
}
