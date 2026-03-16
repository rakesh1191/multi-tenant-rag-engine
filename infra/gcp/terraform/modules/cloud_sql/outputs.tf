output "connection_name"       { value = google_sql_database_instance.main.connection_name; sensitive = true }
output "private_ip"            { value = google_sql_database_instance.main.private_ip_address; sensitive = true }
output "db_password_secret_id" { value = google_secret_manager_secret.db_password.secret_id }
output "db_user"               { value = google_sql_user.app.name }
output "db_name"               { value = google_sql_database.main.name }
