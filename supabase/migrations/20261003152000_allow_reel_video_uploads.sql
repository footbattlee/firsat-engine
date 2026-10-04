update storage.buckets
set allowed_mime_types = array['image/png','image/jpeg','video/mp4']::text[],
    file_size_limit = greatest(coalesce(file_size_limit, 0), 52428800)
where id = 'instagram-media';
