-- Inputs for P/E, forward P/E, dividend yield and live market cap, stored on
-- the security profile. Run once in the Supabase SQL Editor, before starting
-- a backend that reads these columns.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS "epsTrailing" double precision;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS "epsForward" double precision;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS "dividendRate" double precision;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS "sharesOutstanding" double precision;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS "netAssets" double precision;

-- Optional, one time only: age the stored profiles so the next refresh
-- re-fetches all of them and fills the new columns straight away. Without it
-- each profile fills in when it next turns 7 days old.
-- UPDATE public.profiles SET "date" = "date" - interval '7 days';
