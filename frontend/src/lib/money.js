/** Money as the app shows it everywhere: the browser's locale, the loan's currency (INR unless stated). */
export const formatAmount = (amount, currency = 'INR') => {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(amount))
  } catch {
    return `${amount} ${currency}`
  }
}
