import { useEffect, useState } from 'react'
import { api } from './api/client'

export default function App() {
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

  return (
    <main className="page">
      <header className="page__header">
        <h1>Graphite Beauty Salon</h1>
        <p>Выберите услугу, чтобы записаться</p>
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

      {categories.map((category) => (
        <section key={category.slug} className="category">
          <h2>{category.name}</h2>
          <ul className="services">
            {category.services.map((service) => (
              <li key={service.slug} className="service">
                <strong>{service.name}</strong>
                {service.description && <span>{service.description}</span>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  )
}
