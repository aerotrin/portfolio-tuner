


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "hypopg" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "index_advisor" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE TYPE "public"."securitytype" AS ENUM (
    'INDEX',
    'COMMODITY',
    'CRYPTO',
    'FOREX',
    'STOCK',
    'ETF',
    'BOND',
    'GIC',
    'MUTUAL_FUND',
    'REAL_ESTATE',
    'REIT',
    'CASH',
    'OTHER',
    'UNKNOWN'
);


ALTER TYPE "public"."securitytype" OWNER TO "postgres";


CREATE TYPE "public"."transactionkind" AS ENUM (
    'BUY',
    'PURCHASE',
    'SPLIT',
    'DISBURSE',
    'SELL',
    'SOLD',
    'EXPIRED',
    'REDEEMED',
    'EXCHANGE',
    'CONTRIB',
    'EFT',
    'TRANSFER',
    'TRANSF_IN',
    'WITHDRAWAL',
    'DIVIDEND',
    'INTEREST',
    'TAX',
    'HST',
    'FEE'
);


ALTER TYPE "public"."transactionkind" OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."accounts" (
    "id" "text" NOT NULL,
    "number" "text" NOT NULL,
    "owner" "uuid" NOT NULL,
    "type" "text" NOT NULL,
    "currency" "text" NOT NULL,
    "tax_status" "text" NOT NULL,
    "benchmark" "text" NOT NULL,
    "last_modified" timestamp with time zone NOT NULL,
    "name" "text"
);


ALTER TABLE "public"."accounts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bars" (
    "symbol" "text" NOT NULL,
    "date" "date" NOT NULL,
    "open" double precision NOT NULL,
    "high" double precision NOT NULL,
    "low" double precision NOT NULL,
    "close" double precision NOT NULL,
    "volume" double precision NOT NULL
);


ALTER TABLE "public"."bars" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bars_sync_state" (
    "symbol" "text" NOT NULL,
    "last_bar_date" "date",
    "last_checked_at" timestamp with time zone,
    "last_success_at" timestamp with time zone,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    CONSTRAINT "bars_sync_state_status_check" CHECK (("status" = ANY (ARRAY['ok'::"text", 'skipped'::"text", 'error'::"text", 'pending'::"text"])))
);


ALTER TABLE "public"."bars_sync_state" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."global_rates" (
    "id" bigint NOT NULL,
    "date" timestamp with time zone,
    "rf_rate" double precision,
    "fx_rate" double precision
);


ALTER TABLE "public"."global_rates" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."global_rates_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."global_rates_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."global_rates_id_seq" OWNED BY "public"."global_rates"."id";



CREATE TABLE IF NOT EXISTS "public"."profiles" (
    "symbol" "text" NOT NULL,
    "name" "text",
    "date" timestamp with time zone,
    "type" "text",
    "exchange" "text",
    "currency" "text",
    "marketCap" double precision,
    "beta" double precision,
    "lastDividend" double precision,
    "averageVolume" double precision,
    "yearHigh" double precision,
    "yearLow" double precision,
    "isin" "text",
    "cusip" "text",
    "industry" "text",
    "sector" "text",
    "country" "text"
);


ALTER TABLE "public"."profiles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."quotes" (
    "symbol" "text" NOT NULL,
    "name" "text",
    "exchange" "text",
    "open" double precision,
    "high" double precision,
    "low" double precision,
    "close" double precision,
    "currency" "text",
    "volume" double precision,
    "change" double precision,
    "change_percent" double precision,
    "previousClose" double precision,
    "timestamp" timestamp with time zone
);


ALTER TABLE "public"."quotes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."transactions" (
    "id" "text" NOT NULL,
    "account_id" "text" NOT NULL,
    "account_number" "text" NOT NULL,
    "transaction_date" timestamp with time zone NOT NULL,
    "settlement_date" timestamp with time zone,
    "transaction_type" "text" NOT NULL,
    "symbol" "text",
    "market" "text",
    "description" "text" NOT NULL,
    "quantity" integer,
    "currency" "text",
    "price" double precision,
    "commission" double precision,
    "exchange_rate" double precision,
    "fees_paid" double precision NOT NULL,
    "amount" double precision NOT NULL
);


ALTER TABLE "public"."transactions" OWNER TO "postgres";


ALTER TABLE ONLY "public"."global_rates" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."global_rates_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."accounts"
    ADD CONSTRAINT "accounts_number_key" UNIQUE ("number");



ALTER TABLE ONLY "public"."accounts"
    ADD CONSTRAINT "accounts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bars"
    ADD CONSTRAINT "bars_pkey" PRIMARY KEY ("symbol", "date");



ALTER TABLE ONLY "public"."bars_sync_state"
    ADD CONSTRAINT "bars_sync_state_pkey" PRIMARY KEY ("symbol");



ALTER TABLE ONLY "public"."global_rates"
    ADD CONSTRAINT "global_rates_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("symbol");



ALTER TABLE ONLY "public"."quotes"
    ADD CONSTRAINT "quotes_pkey" PRIMARY KEY ("symbol");



ALTER TABLE ONLY "public"."transactions"
    ADD CONSTRAINT "transactions_pkey" PRIMARY KEY ("id");



CREATE INDEX "bars_date_idx" ON "public"."bars" USING "btree" ("date");



CREATE INDEX "ix_bars_symbol_date" ON "public"."bars" USING "btree" ("symbol", "date");



CREATE INDEX "ix_transactions_account_number" ON "public"."transactions" USING "btree" ("account_number");



ALTER TABLE ONLY "public"."accounts"
    ADD CONSTRAINT "accounts_owner_fkey" FOREIGN KEY ("owner") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bars"
    ADD CONSTRAINT "fk_bars_symbol_sync_state" FOREIGN KEY ("symbol") REFERENCES "public"."bars_sync_state"("symbol") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."transactions"
    ADD CONSTRAINT "transactions_account_id_fkey" FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE CASCADE;



ALTER TABLE "public"."accounts" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "accounts_delete" ON "public"."accounts" FOR DELETE USING (("owner" = "auth"."uid"()));



CREATE POLICY "accounts_insert" ON "public"."accounts" FOR INSERT WITH CHECK (("owner" = "auth"."uid"()));



CREATE POLICY "accounts_select" ON "public"."accounts" FOR SELECT USING (("owner" = "auth"."uid"()));



CREATE POLICY "accounts_update" ON "public"."accounts" FOR UPDATE USING (("owner" = "auth"."uid"()));



ALTER TABLE "public"."bars" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "bars_read" ON "public"."bars" FOR SELECT TO "authenticated" USING (true);



ALTER TABLE "public"."bars_sync_state" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "bars_sync_state_read" ON "public"."bars_sync_state" FOR SELECT TO "authenticated" USING (true);



ALTER TABLE "public"."global_rates" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "global_rates_read" ON "public"."global_rates" FOR SELECT TO "authenticated" USING (true);



ALTER TABLE "public"."profiles" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "profiles_read" ON "public"."profiles" FOR SELECT TO "authenticated" USING (true);



ALTER TABLE "public"."quotes" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "quotes_read" ON "public"."quotes" FOR SELECT TO "authenticated" USING (true);



ALTER TABLE "public"."transactions" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "transactions_delete" ON "public"."transactions" FOR DELETE USING (("account_id" IN ( SELECT "accounts"."id"
   FROM "public"."accounts"
  WHERE ("accounts"."owner" = "auth"."uid"()))));



CREATE POLICY "transactions_insert" ON "public"."transactions" FOR INSERT WITH CHECK (("account_id" IN ( SELECT "accounts"."id"
   FROM "public"."accounts"
  WHERE ("accounts"."owner" = "auth"."uid"()))));



CREATE POLICY "transactions_select" ON "public"."transactions" FOR SELECT USING (("account_id" IN ( SELECT "accounts"."id"
   FROM "public"."accounts"
  WHERE ("accounts"."owner" = "auth"."uid"()))));



CREATE POLICY "transactions_update" ON "public"."transactions" FOR UPDATE USING (("account_id" IN ( SELECT "accounts"."id"
   FROM "public"."accounts"
  WHERE ("accounts"."owner" = "auth"."uid"()))));





ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";


















































































































































































































GRANT ALL ON TABLE "public"."accounts" TO "anon";
GRANT ALL ON TABLE "public"."accounts" TO "authenticated";
GRANT ALL ON TABLE "public"."accounts" TO "service_role";



GRANT ALL ON TABLE "public"."bars" TO "anon";
GRANT ALL ON TABLE "public"."bars" TO "authenticated";
GRANT ALL ON TABLE "public"."bars" TO "service_role";



GRANT ALL ON TABLE "public"."bars_sync_state" TO "anon";
GRANT ALL ON TABLE "public"."bars_sync_state" TO "authenticated";
GRANT ALL ON TABLE "public"."bars_sync_state" TO "service_role";



GRANT ALL ON TABLE "public"."global_rates" TO "anon";
GRANT ALL ON TABLE "public"."global_rates" TO "authenticated";
GRANT ALL ON TABLE "public"."global_rates" TO "service_role";



GRANT ALL ON SEQUENCE "public"."global_rates_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."global_rates_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."global_rates_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."profiles" TO "anon";
GRANT ALL ON TABLE "public"."profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."profiles" TO "service_role";



GRANT ALL ON TABLE "public"."quotes" TO "anon";
GRANT ALL ON TABLE "public"."quotes" TO "authenticated";
GRANT ALL ON TABLE "public"."quotes" TO "service_role";



GRANT ALL ON TABLE "public"."transactions" TO "anon";
GRANT ALL ON TABLE "public"."transactions" TO "authenticated";
GRANT ALL ON TABLE "public"."transactions" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































