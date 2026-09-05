/** Radix tab strips (spec §5): 13px muted, the active one in text colour
 *  with a 2px accent underline. `overflow-x-auto` so a trigger scrolls out
 *  of the strip rather than wrapping at 390px (responsive.test.tsx). */
export const TAB_LIST_CLASS = 'mb-4 flex overflow-x-auto border-b border-border'
export const TAB_CLASS = '-mb-px shrink-0 whitespace-nowrap border-b-2 '
  + 'border-transparent px-3 py-2 text-[13px] text-text-muted hover:text-text '
  + 'data-[state=active]:border-accent data-[state=active]:text-text'
