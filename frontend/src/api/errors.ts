export class ApiError extends Error {
  constructor(
    public readonly kind: string,
    public readonly userMessage: string,
    public readonly httpStatus: number,
    public readonly raw?: unknown,
  ) {
    super(userMessage);
    this.name = 'ApiError';
  }
}
