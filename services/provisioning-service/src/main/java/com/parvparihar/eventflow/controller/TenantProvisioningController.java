package com.parvparihar.eventflow.controller;

import com.parvparihar.eventflow.model.TenantProvisionRequest;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/api/v1/tenants")
public class TenantProvisioningController {

    private final Map<String, Map<String, Object>> tenantStore = new ConcurrentHashMap<>();

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {
        return ResponseEntity.ok(Map.of(
                "status", "ok",
                "service", "provisioning-service",
                "tenantsTracked", tenantStore.size()
        ));
    }

    @PostMapping("/provision")
    public ResponseEntity<Map<String, Object>> provision(@Valid @RequestBody TenantProvisionRequest request) {
        String eventId = UUID.randomUUID().toString();
        Map<String, Object> record = Map.of(
                "eventId", eventId,
                "tenantId", request.tenantId(),
                "plan", request.plan(),
                "region", request.region(),
                "status", "PROVISIONING_DISPATCHED",
                "topic", "tenant.provisioning.requested",
                "dispatchedAt", Instant.now().toString()
        );
        tenantStore.put(request.tenantId(), record);
        return ResponseEntity.accepted().body(record);
    }

    @GetMapping("/{tenantId}")
    public ResponseEntity<Map<String, Object>> getTenant(@PathVariable String tenantId) {
        Map<String, Object> record = tenantStore.get(tenantId);
        if (record == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(record);
    }
}
