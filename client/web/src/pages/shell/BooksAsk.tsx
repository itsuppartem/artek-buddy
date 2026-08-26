export function BooksAsk({
  books,
  disabled,
  onAsk,
}: {
  books: { slug: string; name: string }[];
  disabled?: boolean;
  onAsk: (name: string) => void;
}) {
  if (!books.length) return null;
  return (
    <div data-testid="books-ask" className="mb-2 flex flex-wrap gap-2">
      {books.map((book) => (
        <button
          key={book.slug}
          type="button"
          data-testid={`book-ask-${book.slug}`}
          aria-label={`Run ${book.name}`}
          disabled={disabled}
          onClick={() => onAsk(book.name)}
          className="rounded-[8px] border border-hairline bg-raised px-2.5 py-1 text-[13px] text-paper hover:bg-plate disabled:opacity-40"
        >
          {book.name}
        </button>
      ))}
    </div>
  );
}
