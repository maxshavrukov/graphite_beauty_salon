// Шаг 1: выбор услуги. Показывает категории, клик по услуге вызывает
// onSelect(service). Сам ничего не загружает: данные приходят сверху.
export default function ServiceStep({ categories, onSelect }) {
  return (
    <>
      <h2 className="step__title">Выберите услугу</h2>

      {categories.map((category) => (
        <section key={category.slug} className="category">
          <h3>{category.name}</h3>
          <ul className="services">
            {category.services.map((service) => (
              <li key={service.slug}>
                <button
                  type="button"
                  className="service"
                  onClick={() => onSelect(service)}
                >
                  <strong>{service.name}</strong>
                  {service.description && <span>{service.description}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  )
}
