--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (Debian 16.9-1.pgdg120+1)
-- Dumped by pg_dump version 16.9 (Debian 16.9-1.pgdg120+1)

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

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    key_id text NOT NULL,
    secret_hash text NOT NULL,
    label text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone,
    revoked boolean DEFAULT false NOT NULL
);


ALTER TABLE public.api_keys OWNER TO mcp;

--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.chat_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    session_id uuid NOT NULL,
    role character varying(16) NOT NULL,
    content text NOT NULL,
    tool_name character varying(64),
    tool_args text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.chat_messages OWNER TO mcp;

--
-- Name: client_chat_messages; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.client_chat_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    session_id uuid NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    tool_name text,
    tool_args jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT client_chat_messages_role_check CHECK ((role = ANY (ARRAY['system'::text, 'user'::text, 'assistant'::text, 'tool'::text])))
);


ALTER TABLE public.client_chat_messages OWNER TO mcp;

--
-- Name: client_chat_sessions; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.client_chat_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id text NOT NULL,
    system_prompt text DEFAULT ''::text NOT NULL,
    llm_config_id uuid NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    owner_user_id uuid
);


ALTER TABLE public.client_chat_sessions OWNER TO mcp;

--
-- Name: clients_seen; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.clients_seen (
    client_id character varying(200) NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.clients_seen OWNER TO mcp;

--
-- Name: instructions; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.instructions (
    client_id text NOT NULL,
    command_plain text NOT NULL,
    status text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delivered_at timestamp with time zone,
    completed_at timestamp with time zone,
    hmac_signature text,
    result_cipher bytea,
    id uuid DEFAULT gen_random_uuid() NOT NULL
);


ALTER TABLE public.instructions OWNER TO mcp;

--
-- Name: llm_configs; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.llm_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    base_url text,
    api_key_enc text NOT NULL,
    temperature numeric(3,2) DEFAULT 0.2 NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    owner_user_id uuid,
    api_key text,
    is_active boolean DEFAULT true
);


ALTER TABLE public.llm_configs OWNER TO mcp;

--
-- Name: mcp_clients; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.mcp_clients (
    id text NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE public.mcp_clients OWNER TO mcp;

--
-- Name: mcp_instructions; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.mcp_instructions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id text NOT NULL,
    command_plain text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delivered_at timestamp with time zone,
    completed_at timestamp with time zone
);


ALTER TABLE public.mcp_instructions OWNER TO mcp;

--
-- Name: mcp_results; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.mcp_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    instruction_id uuid NOT NULL,
    client_id text NOT NULL,
    encrypted_result text,
    raw_decrypted text,
    received_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.mcp_results OWNER TO mcp;

--
-- Name: results; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.results (
    id text NOT NULL,
    client_id text NOT NULL,
    raw_encrypted text NOT NULL,
    raw_decrypted text,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    processed boolean DEFAULT false NOT NULL
);


ALTER TABLE public.results OWNER TO mcp;

--
-- Name: users; Type: TABLE; Schema: public; Owner: mcp
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    username character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(20),
    disabled boolean,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.users OWNER TO mcp;

--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: api_keys api_keys_user_id_key_id_key; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_key_id_key UNIQUE (user_id, key_id);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id);


--
-- Name: client_chat_messages client_chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.client_chat_messages
    ADD CONSTRAINT client_chat_messages_pkey PRIMARY KEY (id);


--
-- Name: client_chat_sessions client_chat_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.client_chat_sessions
    ADD CONSTRAINT client_chat_sessions_pkey PRIMARY KEY (id);


--
-- Name: clients_seen clients_seen_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.clients_seen
    ADD CONSTRAINT clients_seen_pkey PRIMARY KEY (client_id);


--
-- Name: instructions instructions_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.instructions
    ADD CONSTRAINT instructions_pkey PRIMARY KEY (id);


--
-- Name: llm_configs llm_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.llm_configs
    ADD CONSTRAINT llm_configs_pkey PRIMARY KEY (id);


--
-- Name: mcp_clients mcp_clients_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.mcp_clients
    ADD CONSTRAINT mcp_clients_pkey PRIMARY KEY (id);


--
-- Name: mcp_instructions mcp_instructions_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.mcp_instructions
    ADD CONSTRAINT mcp_instructions_pkey PRIMARY KEY (id);


--
-- Name: mcp_results mcp_results_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.mcp_results
    ADD CONSTRAINT mcp_results_pkey PRIMARY KEY (id);


--
-- Name: results results_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.results
    ADD CONSTRAINT results_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_api_keys_keyid; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_api_keys_keyid ON public.api_keys USING btree (key_id);


--
-- Name: idx_api_keys_user; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_api_keys_user ON public.api_keys USING btree (user_id);


--
-- Name: idx_ccm_session_created; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_ccm_session_created ON public.client_chat_messages USING btree (session_id, created_at);


--
-- Name: idx_ccs_client_created; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_ccs_client_created ON public.client_chat_sessions USING btree (client_id, created_at DESC);


--
-- Name: idx_chat_messages_created; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_chat_messages_created ON public.chat_messages USING btree (created_at);


--
-- Name: idx_chat_messages_session; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_chat_messages_session ON public.chat_messages USING btree (session_id);


--
-- Name: idx_client_chat_sessions_client; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_client_chat_sessions_client ON public.client_chat_sessions USING btree (client_id);


--
-- Name: idx_instr_client_created; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_instr_client_created ON public.instructions USING btree (client_id, created_at DESC);


--
-- Name: idx_instr_client_status; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_instr_client_status ON public.mcp_instructions USING btree (client_id, status);


--
-- Name: idx_instructions_client_created; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_instructions_client_created ON public.instructions USING btree (client_id, created_at DESC);


--
-- Name: idx_instructions_client_status_created; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_instructions_client_status_created ON public.instructions USING btree (client_id, status, created_at);


--
-- Name: idx_llm_configs_active; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_llm_configs_active ON public.llm_configs USING btree (is_active);


--
-- Name: idx_llm_configs_owner; Type: INDEX; Schema: public; Owner: mcp
--

CREATE INDEX idx_llm_configs_owner ON public.llm_configs USING btree (owner_user_id);


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: chat_messages chat_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.client_chat_sessions(id) ON DELETE CASCADE;


--
-- Name: client_chat_messages client_chat_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.client_chat_messages
    ADD CONSTRAINT client_chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.client_chat_sessions(id) ON DELETE CASCADE;


--
-- Name: client_chat_sessions client_chat_sessions_llm_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.client_chat_sessions
    ADD CONSTRAINT client_chat_sessions_llm_config_id_fkey FOREIGN KEY (llm_config_id) REFERENCES public.llm_configs(id) ON DELETE SET NULL;


--
-- Name: chat_messages fk_chat_messages_session; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT fk_chat_messages_session FOREIGN KEY (session_id) REFERENCES public.client_chat_sessions(id) ON DELETE CASCADE;


--
-- Name: client_chat_sessions fk_chat_sessions_llm_config; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.client_chat_sessions
    ADD CONSTRAINT fk_chat_sessions_llm_config FOREIGN KEY (llm_config_id) REFERENCES public.llm_configs(id) ON DELETE SET NULL;


--
-- Name: llm_configs llm_configs_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.llm_configs
    ADD CONSTRAINT llm_configs_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: mcp_instructions mcp_instructions_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.mcp_instructions
    ADD CONSTRAINT mcp_instructions_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.mcp_clients(id) ON DELETE CASCADE;


--
-- Name: mcp_results mcp_results_instruction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mcp
--

ALTER TABLE ONLY public.mcp_results
    ADD CONSTRAINT mcp_results_instruction_id_fkey FOREIGN KEY (instruction_id) REFERENCES public.mcp_instructions(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

