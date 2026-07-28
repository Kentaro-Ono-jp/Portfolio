# Independent review cleanup

<!-- ips-role: procedure -->
<!-- ips-rule: review-cleanup -->

## Read when

Read this file immediately after publishing the review's single verdict
comment.

## Procedure

1. Require the deletion target to be the already verified, uniquely named
   direct child created for this review under the platform temporary root.
2. Use the environment's ordinary scoped deletion mechanism first.
3. If shell or execution policy rejects it, use a standard-library directory
   API in the same process against that exact validated path only.
4. If deletion fails only on read-only descendants, revalidate that every
   residual entry remains below the fixed root, do not traverse reparse-point
   targets, clear only the `ReadOnly` attribute with the same process's
   standard library, and retry the same root.
5. If failure is solely Windows path length, retry with standard-library
   extended-length path handling.
6. Do not change access-control lists, take ownership, terminate processes, or
   broaden the deletion target.
7. Verify the temporary path no longer exists.
8. In the review task's final response, report the verdict URL and actual
   cleanup result.

If cleanup fails, report the exact limitation and remaining path. Do not make
a second GitHub write.

## Completion

This state always ends the review task. Cleanup success or failure never routes
back to implementation from the review agent.

## Return

There is no lifecycle return. Report the final cleanup result and end the
independent review task.
