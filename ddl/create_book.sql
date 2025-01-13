CREATE TABLE IF NOT EXISTS public.book
(
    isbn character varying(13) COLLATE pg_catalog."default" NOT NULL,
    title character varying(200) COLLATE pg_catalog."default" NOT NULL,
    author character varying(150) COLLATE pg_catalog."default" NOT NULL,
    description text COLLATE pg_catalog."default",
    published_date character varying(50) COLLATE pg_catalog."default",
    page_count integer,
    thumbnail character varying(300) COLLATE pg_catalog."default",
    categories text[] COLLATE pg_catalog."default",
    CONSTRAINT book_pkey PRIMARY KEY (isbn)
)