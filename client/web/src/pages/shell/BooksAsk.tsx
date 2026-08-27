export function BooksAsk({
  books,
  disabled,
  onAsk,
  onDismiss,
}: {
  books: { slug: string; name: string }[];
  disabled?: boolean;
  onAsk: (name: string) => void;
  onDismiss: (slug: string) => void;
}) {
  if (!books.length) return null;
  return (
    <div data-testid="books-ask" className="mb-2 flex flex-wrap gap-2">
      {books.map((book) => (
        <span
          key={book.slug}
          className="flex items-center gap-1 rounded-[8px] border border-hairline bg-raised py-0.5 pl-2.5 pr-1 text-[13px] text-paper"
        >
          <button
            type="button"
            data-testid={`book-ask-${book.slug}`}
            aria-label={`Run ${book.name}`}
            disabled={disabled}
            onClick={() => onAsk(book.name)}
            className="py-0.5 text-paper hover:text-tan disabled:opacity-40"
          >
            {book.name}
          </button>
          <button
            type="button"
            data-testid={`book-ask-${book.slug}-remove`}
            aria-label={`Remove ${book.name}`}
            disabled={disabled}
            onClick={() => onDismiss(book.slug)}
            className="px-1.5 py-0.5 text-mute hover:text-paper disabled:opacity-40"
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}
