/**
 * The one table style (spec §5): 10px uppercase headers on the raised band,
 * tabular numerals right-aligned, 32px rows on hairline dividers, hover to
 * raised, the selected row accent-tinted. `DataTable` uses these, and every
 * hand-rolled table (the moves card, the ladder, sensitivity, the standings,
 * the modal's components) imports them so it matches class-for-class.
 */
export const TABLE_CLASS = 'w-full border-collapse'
export const THEAD_CLASS = 'bg-raised'
const TH = 'label h-8 whitespace-nowrap border-b border-border px-2.5 '
  + 'align-middle'
const TD = 'h-8 px-2.5 py-1.5 align-middle'

export function thClass(numeric = false): string {
  return `${TH} ${numeric ? 'text-right' : 'text-left'}`
}

export function tdClass(numeric = false): string {
  return numeric ? `${TD} tn text-right` : TD
}

export const TR_CLASS = 'border-b border-divider hover:bg-raised'
export const TR_SELECTED_CLASS = 'bg-accent-tint'
/** The row an expand control opened: raised, so it reads as the row's own. */
export const TR_EXPANDED_CLASS = 'border-b border-divider bg-raised'
