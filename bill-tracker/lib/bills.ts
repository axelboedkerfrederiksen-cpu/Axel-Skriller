export type BillStatus = 'unpaid' | 'paid';
export type Bill = {
  id: string;
  payee: string;
  amountCents: number;
  dueDate: string;
  status: BillStatus;
};
export type BillDraft = {
  payee: string;
  amount: string;
  dueDate: string;
  status: BillStatus;
};
export type BillErrors = Partial<Record<keyof BillDraft, string>>;
export const emptyDraft: BillDraft = {
  payee: '',
  amount: '',
  dueDate: '',
  status: 'unpaid',
};
export const currency = 'USD';
const moneyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency,
});
export function formatMoney(cents: number) {
  return moneyFormatter.format(cents / 100);
}

// Integer cents keep addition exact, including values like $0.10 and $0.20.
export function parseAmount(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
  const [whole, fraction = ''] = normalized.split('.');
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  return Number.isSafeInteger(cents) && cents > 0 && cents <= 999999999
    ? cents
    : null;
}
export function isValidDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000'))
    return false;
  const date = new Date(`${value}T12:00:00Z`);
  return (
    !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}
export function formatDueDate(value: string) {
  // Explicit UTC preserves the calendar date in every viewer's timezone.
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T12:00:00Z`));
}
export function validateDraft(draft: BillDraft): BillErrors {
  const errors: BillErrors = {};
  if (!draft.payee.trim()) errors.payee = 'Enter a payee or description.';
  else if (draft.payee.trim().length > 120)
    errors.payee = 'Use 120 characters or fewer.';
  if (parseAmount(draft.amount) === null)
    errors.amount = 'Enter $0.01–$9,999,999.99, with up to 2 decimal places.';
  if (!isValidDate(draft.dueDate)) errors.dueDate = 'Choose a valid due date.';
  if (draft.status !== 'paid' && draft.status !== 'unpaid')
    errors.status = 'Choose a payment status.';
  return errors;
}
export type BillAction =
  | { type: 'add'; bill: Bill }
  | { type: 'toggle'; id: string };
// React owns the store's lifetime. No data goes to browser storage or a server.
export function billsReducer(bills: Bill[], action: BillAction): Bill[] {
  if (action.type === 'add') return [...bills, action.bill];
  return bills.map((bill) =>
    bill.id === action.id
      ? { ...bill, status: bill.status === 'paid' ? 'unpaid' : 'paid' }
      : bill,
  );
}
export function sortedBills(bills: Bill[]) {
  // Equal dates retain insertion order; payment changes never reorder bills.
  return [...bills].sort((a, b) => a.dueDate.localeCompare(b.dueDate));
}
export function summarizeBills(bills: Bill[]) {
  return bills.reduce(
    (summary, bill) => {
      summary[bill.status] += bill.amountCents;
      summary[bill.status === 'paid' ? 'paidCount' : 'unpaidCount'] += 1;
      return summary;
    },
    { paid: 0, unpaid: 0, paidCount: 0, unpaidCount: 0 },
  );
}
