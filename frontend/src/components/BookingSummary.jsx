import { formatDateLong, formatPrice } from '../utils/format'

// Что именно выбрал клиент: показывается над формой и на экране «заявка принята».
export default function BookingSummary({ service, date, time, selected }) {
  return (
    <dl className="summary">
      <div className="summary__row">
        <dt>Услуга</dt>
        <dd>{service.name}</dd>
      </div>
      <div className="summary__row">
        <dt>Дата и время</dt>
        <dd>
          {formatDateLong(date)}, {time}
        </dd>
      </div>
      <div className="summary__row">
        <dt>Мастер</dt>
        <dd>{selected.master.name}</dd>
      </div>
      <div className="summary__row">
        <dt>Стоимость</dt>
        <dd>{formatPrice(selected.price)}</dd>
      </div>
    </dl>
  )
}
