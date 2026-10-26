import { useEffect, useState } from 'react'
import { api } from './api/client'
import ContactStep from './components/ContactStep'
import DateStep from './components/DateStep'
import MasterStep from './components/MasterStep'
import ServiceStep from './components/ServiceStep'
import SuccessStep from './components/SuccessStep'
import TimeStep from './components/TimeStep'

export default function App() {
  // Всё, что клиент уже выбрал, лежит здесь.
  const [service, setService] = useState(null)
  const [date, setDate] = useState(null)
  const [time, setTime] = useState(null)
  const [master, setMaster] = useState(null) // {master, price}
  const [contact, setContact] = useState({ name: '', phone: '' })

  // Ответ сервера после отправки заявки (не null = заявка принята).
  const [result, setResult] = useState(null)

  // Причина, по которой пришлось сбросить время (его заняли), и счётчик
  // для повторной загрузки списка времени.
  const [notice, setNotice] = useState(null)
  const [timesVersion, setTimesVersion] = useState(0)

  const [categories, setCategories] = useState([])
  const [status, setStatus] = useState('loading') // loading | ready | error

  useEffect(() => {
    // Флаг нужен, чтобы не писать в состояние после размонтирования
    // (в режиме разработки React запускает эффект дважды).
    let cancelled = false

    api
      .getCategories()
      .then((data) => {
        if (cancelled) return
        setCategories(data)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Каждый следующий выбор зависит от предыдущего, поэтому смена
  // услуги или даты сбрасывает всё, что выбрано после неё.
  function chooseService(chosen) {
    setService(chosen)
    setDate(null)
    setTime(null)
    setMaster(null)
    setNotice(null)
  }

  function chooseDate(chosen) {
    setDate(chosen)
    setTime(null)
    setMaster(null)
    setNotice(null)
  }

  function chooseTime(chosen) {
    setTime(chosen)
    setMaster(null)
    setNotice(null)
  }

  function backToServices() {
    setService(null)
    setDate(null)
    setTime(null)
    setMaster(null)
    setNotice(null)
  }

  // Сервер ответил, что время недоступно: сбрасываем время и мастера,
  // обновляем список времени и объясняем клиенту, что случилось.
  function handleConflict(message) {
    setTime(null)
    setMaster(null)
    setNotice(message)
    setTimesVersion((version) => version + 1)
  }

  // «Записаться ещё»: возвращаемся к началу, имя и телефон не храним.
  function restart() {
    backToServices()
    setContact({ name: '', phone: '' })
    setResult(null)
  }

  const ready = status === 'ready'

  return (
    <main className="page">
      <header className="page__header">
        <h1>Graphite Beauty Salon</h1>
        <p>Онлайн-запись</p>
      </header>

      {status === 'loading' && <p className="note">Загружаем услуги…</p>}

      {status === 'error' && (
        <p className="note note--error">
          Не удалось загрузить услуги. Попробуйте обновить страницу.
        </p>
      )}

      {status === 'ready' && categories.length === 0 && (
        <p className="note">Услуг пока нет. Загляните позже.</p>
      )}

      {ready && result && (
        <SuccessStep
          result={result}
          service={service}
          date={date}
          time={time}
          selected={master}
          onRestart={restart}
        />
      )}

      {ready && !result && !service && (
        <ServiceStep categories={categories} onSelect={chooseService} />
      )}

      {ready && !result && service && (
        <DateStep
          service={service}
          selectedDate={date}
          onSelect={chooseDate}
          onBack={backToServices}
        />
      )}

      {ready && !result && service && date && (
        <>
          {notice && <p className="note note--error">{notice}</p>}

          <TimeStep
            service={service}
            date={date}
            selectedTime={time}
            onSelect={chooseTime}
            version={timesVersion}
          />
        </>
      )}

      {ready && !result && service && date && time && (
        <MasterStep
          service={service}
          date={date}
          time={time}
          selected={master}
          onSelect={setMaster}
        />
      )}

      {ready && !result && service && date && time && master && (
        <ContactStep
          service={service}
          date={date}
          time={time}
          selected={master}
          contact={contact}
          onChange={setContact}
          onSuccess={setResult}
          onConflict={handleConflict}
        />
      )}
    </main>
  )
}
