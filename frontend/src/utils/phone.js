// Телефон вводится после фиксированного префикса «+38»: клиент пишет только
// «0990172668». Правила совпадают с проверкой на бэкенде (catalog/phone.py),
// но последнее слово остаётся за сервером.
export const PHONE_LENGTH = 10

// Оставляет только цифры. Если клиент вставил номер целиком
// («+380990172668», «+38 (099) 017-26-68»), префикс уже есть в поле,
// поэтому его отбрасываем.
export function cleanPhoneInput(value) {
  let digits = value.replace(/\D/g, '')

  if (digits.startsWith('380') && digits.length > PHONE_LENGTH) {
    digits = digits.slice(2)
  }

  return digits.slice(0, PHONE_LENGTH)
}

// «0990172668»: десять цифр, первая 0.
export function isValidPhone(digits) {
  return /^0\d{9}$/.test(digits)
}

// «0990172668» -> «+380990172668» (так номер уходит на сервер).
export function toApiPhone(digits) {
  return `+38${digits}`
}
