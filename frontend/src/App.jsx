import { useEffect, useState } from 'react'
import { api } from './api/client'
import DateStep from './components/DateStep'
import ServiceStep from './components/ServiceStep'

export default function App() {
  // Всё, что клиент уже выбрал, лежит здесь. Следующие шаги записи
  // (время, мастер, контакты) будут добавлять сюда свои поля.
  const [service, setService] = useState(null)
  const [date, setDate] = useState(null)

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

  function chooseService(chosen) {
    setService(chosen)
    setDate(null) // другая услуга — другие доступные даты
  }

  function backToServices() {
    setService(null)
    setDate(null)
  }

  return (
    <main className="page">
      <header className="page__header">
        <h1>Graphite Beauty Salon</h1>
        <p>Онлайн-запись</p>
      </header>

      {status === 'loading' && <p className="note">Загружаем услуги…</p>}

      {status === 'error' && (
        <p className="note note--error">
          Не удалось загрузить услуги. Проверьте, что Django запущен
          (python manage.py runserver).
        </p>
      )}

      {status === 'ready' && categories.length === 0 && (
        <p className="note">
          Услуг пока нет. Заполните каталог в админке или выполните
          python manage.py seed_demo.
        </p>
      )}

      {status === 'ready' && !service && (
        <ServiceStep categories={categories} onSelect={chooseService} />
      )}

      {status === 'ready' && service && (
        <DateStep
          service={service}
          selectedDate={date}
          onSelect={setDate}
          onBack={backToServices}
        />
      )}
    </main>
  )
}
