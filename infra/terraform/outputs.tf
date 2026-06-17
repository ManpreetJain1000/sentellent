output "backend_service_name" {
  value = aws_ecs_service.backend.name
}

output "amplify_app_id" {
  value = aws_amplify_app.frontend.id
}

output "amplify_frontend_url" {
  value = local.amplify_frontend_url
}

output "api_gateway_endpoint" {
  value = aws_apigatewayv2_api.backend.api_endpoint
}

output "postgres_endpoint" {
  value = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.redis.cache_nodes[0].address
}
