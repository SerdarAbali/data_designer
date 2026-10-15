/**
 * Discipline model modules historically imported their HTTP helpers from here.
 * The implementation now lives in `../apiClient`; re-exported so those imports
 * keep working while there is a single shared client.
 */
export { ApiError, api, csrfToken, describeApiDetail, list } from "../apiClient";
