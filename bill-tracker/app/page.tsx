'use client';

import { useReducer, useRef, useState, type FormEvent } from 'react';
import {
  ArrowDown,
  Check,
  CheckCheck,
  CircleHelp,
  Plus,
  ReceiptText,
  Undo2,
  Wallet,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from '@/components/ui/empty';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from '@/components/ui/table';
import {
  billsReducer,
  currency,
  emptyDraft,
  formatDueDate,
  formatMoney,
  parseAmount,
  sortedBills,
  summarizeBills,
  validateDraft,
  type Bill,
  type BillDraft,
  type BillErrors,
} from '@/lib/bills';

export default function Home() {
  const [bills, dispatch] = useReducer(billsReducer, []);
  const [draft, setDraft] = useState<BillDraft>({ ...emptyDraft });
  const [errors, setErrors] = useState<BillErrors>({});
  const [announcement, setAnnouncement] = useState('');
  const formRef = useRef<HTMLFormElement>(null);
  const summary = summarizeBills(bills);
  const orderedBills = sortedBills(bills);

  function updateField<K extends keyof BillDraft>(
    field: K,
    value: BillDraft[K],
  ) {
    setDraft((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }
  function addBill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateDraft(draft);
    setErrors(nextErrors);
    const firstError = Object.keys(nextErrors)[0];
    if (firstError) {
      formRef.current?.querySelector<HTMLElement>(`#${firstError}`)?.focus();
      return;
    }
    const bill: Bill = {
      id: crypto.randomUUID(),
      payee: draft.payee.trim(),
      amountCents: parseAmount(draft.amount)!,
      dueDate: draft.dueDate,
      status: draft.status,
    };
    dispatch({ type: 'add', bill });
    setDraft({ ...emptyDraft });
    setAnnouncement(
      `${bill.payee} added for ${formatMoney(bill.amountCents)}.`,
    );
    formRef.current?.querySelector<HTMLInputElement>('#payee')?.focus();
  }
  function toggleBill(bill: Bill) {
    dispatch({ type: 'toggle', id: bill.id });
    setAnnouncement(
      `${bill.payee} marked as ${bill.status === 'paid' ? 'unpaid' : 'paid'}.`,
    );
  }

  return (
    <div className="app-shell">
      <a href="#add-bill" className="skip-link">
        Skip to add a bill
      </a>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-icon">
              <ReceiptText aria-hidden="true" size={22} />
            </span>
            <span>Bill tracker</span>
          </div>
        </div>
      </header>
      <main className="workspace">
        <div className="page-heading">
          <div>
            <p className="eyebrow">YOUR BUSINESS</p>
            <h1>Bills at a glance</h1>
          </div>
          <span className="currency-note">All amounts in {currency}</span>
        </div>
        <section className="summary-grid" aria-label="Bill totals">
          <div className="summary-card unpaid-summary">
            <div className="summary-top">
              <h2>Total unpaid</h2>
              <Wallet size={22} aria-hidden="true" />
            </div>
            <p className="summary-amount" data-testid="unpaid-total">
              {formatMoney(summary.unpaid)}
            </p>
            <p className="summary-detail">
              {summary.unpaidCount}{' '}
              {summary.unpaidCount === 1 ? 'bill' : 'bills'} to pay
            </p>
          </div>
          <div className="summary-card paid-summary">
            <div className="summary-top">
              <h2>Total paid</h2>
              <span className="paid-icon">
                <CheckCheck size={22} aria-hidden="true" />
              </span>
            </div>
            <p className="summary-amount" data-testid="paid-total">
              {formatMoney(summary.paid)}
            </p>
            <p className="summary-detail">
              {summary.paidCount} {summary.paidCount === 1 ? 'bill' : 'bills'}{' '}
              paid
            </p>
          </div>
        </section>
        <p className="session-notice">
          <CircleHelp size={17} aria-hidden="true" />
          <span>
            Bills are kept for this session. Refreshing or closing this page
            clears them.
          </span>
        </p>
        <div className="content-grid">
          <section className="panel form-panel" aria-labelledby="add-bill">
            <div className="panel-heading">
              <h2 id="add-bill">Add a bill</h2>
              <Plus size={20} aria-hidden="true" />
            </div>
            <form ref={formRef} onSubmit={addBill} noValidate>
              <div className="form-field">
                <label htmlFor="payee">Payee or description</label>
                <Input
                  id="payee"
                  name="payee"
                  className="bill-input"
                  placeholder="e.g. Office rent"
                  value={draft.payee}
                  onChange={(event) => updateField('payee', event.target.value)}
                  maxLength={120}
                  required
                  aria-invalid={Boolean(errors.payee)}
                  aria-describedby={errors.payee ? 'payee-error' : undefined}
                />
                {errors.payee && (
                  <p className="field-error" id="payee-error">
                    {errors.payee}
                  </p>
                )}
              </div>
              <div className="form-field">
                <label htmlFor="amount">
                  Amount <span className="label-note">({currency})</span>
                </label>
                <div className="amount-input">
                  <span aria-hidden="true">$</span>
                  <Input
                    id="amount"
                    name="amount"
                    className="bill-input"
                    type="text"
                    inputMode="decimal"
                    placeholder="0.00"
                    value={draft.amount}
                    onChange={(event) =>
                      updateField('amount', event.target.value)
                    }
                    maxLength={16}
                    required
                    aria-invalid={Boolean(errors.amount)}
                    aria-describedby={
                      errors.amount ? 'amount-error' : undefined
                    }
                  />
                </div>
                {errors.amount && (
                  <p className="field-error" id="amount-error">
                    {errors.amount}
                  </p>
                )}
              </div>
              <div className="form-field">
                <label htmlFor="dueDate">Due date</label>
                <Input
                  id="dueDate"
                  name="dueDate"
                  className="bill-input date-input"
                  type="date"
                  min="0001-01-01"
                  max="9999-12-31"
                  value={draft.dueDate}
                  onChange={(event) =>
                    updateField('dueDate', event.target.value)
                  }
                  required
                  aria-invalid={Boolean(errors.dueDate)}
                  aria-describedby={
                    errors.dueDate ? 'dueDate-error' : undefined
                  }
                />
                {errors.dueDate && (
                  <p className="field-error" id="dueDate-error">
                    {errors.dueDate}
                  </p>
                )}
              </div>
              <fieldset className="form-field status-field">
                <legend id="status-label">Payment status</legend>
                <RadioGroup
                  name="status"
                  className="status-options"
                  aria-labelledby="status-label"
                  value={draft.status}
                  onValueChange={(value) =>
                    updateField('status', value as BillDraft['status'])
                  }
                >
                  <label
                    className={`status-choice ${draft.status === 'unpaid' ? 'is-selected' : ''}`}
                    htmlFor="status-unpaid"
                  >
                    <RadioGroupItem id="status-unpaid" value="unpaid" />
                    Unpaid
                  </label>
                  <label
                    className={`status-choice ${draft.status === 'paid' ? 'is-selected' : ''}`}
                    htmlFor="status-paid"
                  >
                    <RadioGroupItem id="status-paid" value="paid" />
                    Paid
                  </label>
                </RadioGroup>
              </fieldset>
              <Button type="submit" className="add-button">
                <Plus size={18} aria-hidden="true" />
                Add bill
              </Button>
            </form>
          </section>
          <section
            className="panel list-panel"
            aria-labelledby="bill-list-heading"
          >
            <div className="list-heading">
              <div className="list-title">
                <h2 id="bill-list-heading">All bills</h2>
                <span className="bill-count">{bills.length}</span>
              </div>
              <span className="sort-note">
                <ArrowDown size={15} aria-hidden="true" />
                Due date, earliest first
              </span>
            </div>
            {orderedBills.length === 0 ? (
              <Empty className="bill-empty">
                <EmptyHeader>
                  <EmptyMedia className="empty-receipt">
                    <ReceiptText size={30} aria-hidden="true" />
                  </EmptyMedia>
                  <EmptyTitle className="empty-title">No bills yet</EmptyTitle>
                  <EmptyDescription className="empty-description">
                    Add your first bill to start keeping track.
                    <br />
                    Your bills and their payment status will appear here.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <Table className="bills-table" role="table">
                <TableCaption className="sr-only">
                  All bills, sorted by due date from earliest to latest. Use the
                  payment button to change a bill’s status.
                </TableCaption>
                <TableHeader role="rowgroup">
                  <TableRow role="row">
                    <TableHead scope="col" role="columnheader">
                      Payee / description
                    </TableHead>
                    <TableHead
                      scope="col"
                      role="columnheader"
                      aria-sort="ascending"
                    >
                      Due date
                    </TableHead>
                    <TableHead
                      scope="col"
                      role="columnheader"
                      className="amount-cell"
                    >
                      Amount
                    </TableHead>
                    <TableHead scope="col" role="columnheader">
                      Status
                    </TableHead>
                    <TableHead scope="col" role="columnheader">
                      <span className="sr-only">Change payment status</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody role="rowgroup">
                  {orderedBills.map((bill) => (
                    <TableRow key={bill.id} role="row">
                      <TableCell className="payee-cell" role="cell">
                        {bill.payee}
                      </TableCell>
                      <TableCell
                        className="date-cell"
                        data-label="Due date"
                        role="cell"
                      >
                        <time dateTime={bill.dueDate}>
                          {formatDueDate(bill.dueDate)}
                        </time>
                      </TableCell>
                      <TableCell
                        className="amount-cell"
                        data-label="Amount"
                        role="cell"
                      >
                        {formatMoney(bill.amountCents)}
                      </TableCell>
                      <TableCell className="status-cell" role="cell">
                        <span className={`status-badge ${bill.status}`}>
                          {bill.status === 'paid' ? (
                            <Check size={14} aria-hidden="true" />
                          ) : (
                            <span className="status-dot" aria-hidden="true" />
                          )}
                          {bill.status === 'paid' ? 'Paid' : 'Unpaid'}
                        </span>
                      </TableCell>
                      <TableCell className="action-cell" role="cell">
                        <Button
                          type="button"
                          variant="outline"
                          className={`payment-button ${bill.status === 'paid' ? 'undo-button' : ''}`}
                          onClick={() => toggleBill(bill)}
                          aria-label={`Mark ${bill.payee} as ${bill.status === 'paid' ? 'unpaid' : 'paid'}`}
                        >
                          {bill.status === 'paid' ? (
                            <Undo2 size={15} aria-hidden="true" />
                          ) : (
                            <Check size={15} aria-hidden="true" />
                          )}
                          {bill.status === 'paid' ? 'Mark unpaid' : 'Mark paid'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        </div>
        <p
          className="activity-message"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {announcement && (
            <>
              <Check size={16} aria-hidden="true" />
              <span>{announcement}</span>
            </>
          )}
        </p>
      </main>
    </div>
  );
}
