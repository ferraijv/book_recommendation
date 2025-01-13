CREATE TABLE IF NOT EXISTS public.user_books
(
    id integer NOT NULL DEFAULT nextval('user_books_id_seq'::regclass),
    user_id integer NOT NULL,
    book_isbn character varying(50) COLLATE pg_catalog."default" NOT NULL,
    rating character varying(50) COLLATE pg_catalog."default",
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_books_pkey PRIMARY KEY (id),
    CONSTRAINT fk_book FOREIGN KEY (book_isbn)
        REFERENCES public.book (isbn) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT fk_user FOREIGN KEY (user_id)
        REFERENCES public."user" (id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)