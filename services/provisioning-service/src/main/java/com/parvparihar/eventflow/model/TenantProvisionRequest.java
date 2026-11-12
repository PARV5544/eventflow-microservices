package com.parvparihar.eventflow.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record TenantProvisionRequest(
        @NotBlank String tenantId,
        @NotBlank @Pattern(regexp = "^(starter|pro|enterprise)$") String plan,
        @NotBlank String region
) {}
