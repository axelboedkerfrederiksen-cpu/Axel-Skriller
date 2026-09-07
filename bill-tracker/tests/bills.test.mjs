import test from 'node:test';
import assert from 'node:assert/strict';
import {
  billsReducer,
  emptyDraft,
  formatDueDate,
  formatMoney,
  isValidDate,
  parseAmount,
  sortedBills,
  summarizeBills,
  validateDraft,
} from '../lib/bills.ts';

const rent = {
  id: 'rent',
  payee: 'Office rent',
  amountCents: 125050,
  dueDate: '2026-10-01',
  status: 'unpaid',
};
const internet = {
  id: 'internet',
  payee: 'Internet',
  amountCents: 5999,
  dueDate: '2026-09-10',
  status: 'paid',
};

test('starts empty and adds both unpaid and already-paid bills', () => {
  assert.deepEqual(summarizeBills([]), {
    paid: 0,
    unpaid: 0,
    paidCount: 0,
    unpaidCount: 0,
  });
  const first = billsReducer([], { type: 'add', bill: rent });
  const second = billsReducer(first, { type: 'add', bill: internet });
  assert.equal(first.length, 1);
  assert.equal(second.length, 2);
  assert.deepEqual(summarizeBills(second), {
    unpaid: 125050,
    paid: 5999,
    unpaidCount: 1,
    paidCount: 1,
  });
});

test('sorts across months and years, preserves ties, and does not mutate the store', () => {
  const bills = [
    rent,
    { ...rent, id: 'next-year', dueDate: '2027-01-01' },
    internet,
    { ...internet, id: 'same-date' },
    { ...rent, id: 'past', dueDate: '2025-12-31' },
  ];
  assert.deepEqual(
    sortedBills(bills).map((bill) => bill.id),
    ['past', 'internet', 'same-date', 'rent', 'next-year'],
  );
  assert.equal(bills[0].id, 'rent');
});

test('one payment action transfers the exact total and a second action restores it', () => {
  const bills = [rent, internet];
  const paid = billsReducer(bills, { type: 'toggle', id: 'rent' });
  assert.deepEqual(summarizeBills(paid), {
    unpaid: 0,
    paid: 131049,
    unpaidCount: 0,
    paidCount: 2,
  });
  assert.equal(bills[0].status, 'unpaid');
  assert.equal(paid[1], internet);
  assert.deepEqual(billsReducer(paid, { type: 'toggle', id: 'rent' }), bills);
  assert.deepEqual(
    sortedBills(paid).map((bill) => bill.id),
    ['internet', 'rent'],
  );
});

test('decimal amounts add exactly and render as money', () => {
  const ten = parseAmount('0.10');
  const twenty = parseAmount('0.20');
  assert.equal(ten + twenty, 30);
  assert.equal(formatMoney(ten + twenty), '$0.30');
  assert.equal(parseAmount(' 1234.5 '), 123450);
  assert.equal(parseAmount('9999999.99'), 999999999);
});

test('rejects empty, negative, zero, non-finite, excessive, and overprecise amounts', () => {
  for (const value of [
    '',
    ' ',
    '-1',
    '0',
    '0.00',
    'NaN',
    'Infinity',
    '1e3',
    '1.234',
    '1,234',
    '10000000',
    '999999999999999999999',
  ]) {
    assert.equal(parseAmount(value), null, value);
  }
});

test('accepts past and leap-day dates, rejects impossible dates, preserves calendar display', () => {
  assert.equal(isValidDate('2024-02-29'), true);
  assert.equal(isValidDate('2020-01-01'), true);
  for (const value of [
    '',
    '2026-02-29',
    '2026-02-30',
    '2026-13-01',
    '2026-04-31',
    '0000-01-01',
    '09/06/2026',
  ])
    assert.equal(isValidDate(value), false, value);
  assert.equal(formatDueDate('2026-01-01'), 'Jan 1, 2026');
});

test('form validation identifies required fields while preserving the draft', () => {
  assert.deepEqual(Object.keys(validateDraft(emptyDraft)), [
    'payee',
    'amount',
    'dueDate',
  ]);
  const draft = {
    payee: '  Office rent  ',
    amount: '1250.50',
    dueDate: '2026-10-01',
    status: 'paid',
  };
  assert.deepEqual(validateDraft(draft), {});
  assert.equal(draft.payee, '  Office rent  ');
  assert.ok(validateDraft({ ...draft, payee: '   ' }).payee);
  assert.ok(validateDraft({ ...draft, payee: 'a'.repeat(121) }).payee);
});
