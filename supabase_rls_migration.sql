-- Review this migration before running. It changes policies only; it does not delete table data.
BEGIN;
-- Intended object path: <tenant_uuid>/<document_uuid>/<safe_filename>

-- Documents: every tenant member can read; only owner/admin can insert. No update/delete API is exposed.
DROP POLICY IF EXISTS documents_member_access ON public.documents;
DROP POLICY IF EXISTS documents_member_select ON public.documents;
DROP POLICY IF EXISTS documents_admin_insert ON public.documents;

CREATE POLICY documents_member_select
ON public.documents FOR SELECT TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id = documents.tenant_id
      AND tm.user_id = (SELECT auth.uid())
  )
);

CREATE POLICY documents_admin_insert
ON public.documents FOR INSERT TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id = documents.tenant_id
      AND tm.user_id = (SELECT auth.uid())
      AND tm.role IN ('owner', 'admin')
  )
);

-- Data sources are visible and manageable only by owner/admin.
DROP POLICY IF EXISTS data_sources_member_access ON public.data_sources;
DROP POLICY IF EXISTS data_sources_admin_select ON public.data_sources;
DROP POLICY IF EXISTS data_sources_admin_insert ON public.data_sources;
DROP POLICY IF EXISTS data_sources_admin_delete ON public.data_sources;

CREATE POLICY data_sources_admin_select
ON public.data_sources FOR SELECT TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id = data_sources.tenant_id
      AND tm.user_id = (SELECT auth.uid())
      AND tm.role IN ('owner', 'admin')
  )
);

CREATE POLICY data_sources_admin_insert
ON public.data_sources FOR INSERT TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id = data_sources.tenant_id
      AND tm.user_id = (SELECT auth.uid())
      AND tm.role IN ('owner', 'admin')
  )
);

CREATE POLICY data_sources_admin_delete
ON public.data_sources FOR DELETE TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id = data_sources.tenant_id
      AND tm.user_id = (SELECT auth.uid())
      AND tm.role IN ('owner', 'admin')
  )
);

-- Private document storage. Any tenant member may read their tenant's files.
-- Only owner/admin may upload. The uploader may delete its own object for failed-upload cleanup; no UPDATE/upsert policy is added.
DROP POLICY IF EXISTS tenant_documents_member_select ON storage.objects;
DROP POLICY IF EXISTS tenant_documents_admin_insert ON storage.objects;
DROP POLICY IF EXISTS tenant_documents_uploader_cleanup ON storage.objects;

CREATE POLICY tenant_documents_member_select
ON storage.objects FOR SELECT TO authenticated
USING (
  bucket_id = 'tenant-documents'
  AND EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id::text = (storage.foldername(name))[1]
      AND tm.user_id = (SELECT auth.uid())
  )
);

CREATE POLICY tenant_documents_admin_insert
ON storage.objects FOR INSERT TO authenticated
WITH CHECK (
  bucket_id = 'tenant-documents'
  AND EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id::text = (storage.foldername(name))[1]
      AND tm.user_id = (SELECT auth.uid())
      AND tm.role IN ('owner', 'admin')
  )
);

CREATE POLICY tenant_documents_uploader_cleanup
ON storage.objects FOR DELETE TO authenticated
USING (
  bucket_id = 'tenant-documents'
  AND owner_id = (SELECT auth.uid()::text)
  AND EXISTS (
    SELECT 1 FROM public.tenant_members tm
    WHERE tm.tenant_id::text = (storage.foldername(name))[1]
      AND tm.user_id = (SELECT auth.uid())
      AND tm.role IN ('owner', 'admin')
  )
);

COMMIT;
