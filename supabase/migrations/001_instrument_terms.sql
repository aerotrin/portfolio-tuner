-- Terms of a manually entered fixed-income instrument (GIC, term deposit),
-- stored on its opening Buy row. Run once in the Supabase SQL Editor.
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS instrument_terms jsonb;
