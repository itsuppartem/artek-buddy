CREATE FUNCTION artek_split_probe(note text DEFAULT 'probe; value') RETURNS integer
LANGUAGE plpgsql
AS $artek$
BEGIN
  -- semicolon in a comment;
  PERFORM 1;
  RETURN 1;
END;
$artek$;
