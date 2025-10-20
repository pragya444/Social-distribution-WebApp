# API Endpoint Documentation

This documentation provides **comprehensive details for every API endpoint**, including when, how, and why to use them; multiple examples (success, minimal, and error); full JSON field tables with types, example values, and purposes; pagination notes; and special considerations.

---

## Base URL

```
http://127.0.0.1:8000/
```

> Replace with production URL if `DJANGO_ENV=production`.

---

## Authentication Endpoints

### POST `/auth/register/`

**When:** When creating a new user account.
**How:** Send a JSON payload with username and password. 
**Why:** To onboard new users.
**Why Not:** Username must be unique.

**Request Headers:**

```
Content-Type: application/json
```

**Request Body Examples:**

**Minimal Registration:**

```json
{
  "username": "alice",
  "password": "secure123",
  "name": "Alice"
}
```

**Full Registration with GitHub:**

```json
{
  "username": "bob",
  "password": "secure123",
  "name": "Bob Smith",
  "github": "bobcodes"
}
```

**Request Fields:**

| Field    | Type   | Example | Purpose |
| -------- | ------ | --------| ------- |
| username | string | "user123" | Unique login identifier |
| password | string | "securePass123" | Account password (min 8 chars) |
| name | string | "user1" | Display name                      |
| github | string | "[https://github.com/user1](https://github.com/user1)" | GitHub username

**Success Response (201 Created):**

```json
{
  "id": "user_1",
  "username": "amit123",
  "name": "Amit Singh",
  "description": "",
  "github": "https://github.com/amit123",
  "profile_picture": "",
  "url": "http://127.0.0.1:8000/authors/user_1",
  "created": "2025-10-19T18:00:00Z"
}
```

**Error Examples:**

* 400: Username already exists
* 400: Validation errors (name blank, password too short)

**Special Notes:** GitHub usernames without full URL are auto-prefixed with `https://github.com/`. Successful registration auto-logs in the user.

---

### POST `/auth/login/`

**When:** Before accessing protected resources.
**How:** Send JSON credentials.
**Why:** Establish a JWT session.
**Why Not:** Should only be used for authentication.

**Request Headers:**

```
Content-Type: application/json
```

**Valid Login:**

```json
{
  "username": "alice",
  "password": "secure123"
}
```

**Invalid Login:**

```json
{
  "username": "alice",
  "password": "wrongpass"
}
```

**Request Fields:**

| Field    | Type   | Example     | Purpose          |
| -------- | ------ | ----------- | ---------------- |
| username | string | "alice"     | Login identifier |
| password | string | "secure123" | Account password |

**Success Response (200 OK):**

```json
{
  "user": {
    "id": "user_1",
    "username": "alice",
    "name": "Alice",
    "url": "http://127.0.0.1:8000/authors/user_1"
  },
  "token": "JWT_TOKEN_HERE"
}
```

**Error Response (400 Bad Request):**

```json
{
  "errors": {
    "error": ["Invalid username or password"]
  }
}
```

---

### POST `/auth/logout/`

**When:** When signing out.
**How:** Send an empty POST request with JWT cookie.
**Why:** Clear authentication session.
**Why Not:** Stateless JWT; server-side token is not invalidated.

**Request Headers:**

```
POST /auth/logout/
Cookie: jwt=YOUR_JWT_TOKEN
```

**Success Response (302 Found):**

* Redirects to `/auth/login/` and clears cookies: `jwt`, `sessionid`, `csrftoken`

**Special Notes:** Can be called without authentication. Client should clear stored tokens.

---

## Users / Profiles

### GET `/authors/<author_id>/`

**When:** To view a user's profile.
**How:** Send GET request with Authorization header.
**Why:** Fetch profile details and entries.
**Why Not:** Returns 403 if unauthenticated for JSON requests.

**Request Headers:**

```
Authorization: Bearer <JWT_TOKEN>
```

**Success Response:**

```json
{
  "id": "user_1",
  "username": "alice",
  "name": "Alice",
  "description": "Software developer",
  "github": "https://github.com/alice",
  "profile_picture": "https://img.example.com/alice.jpg",
  "url": "http://127.0.0.1:8000/authors/user_1",
  "created": "2025-01-01T12:00:00Z",
  "entries": [ ... ],
  "posts_count": 5,
  "followers_count": 10,
  "following_count": 3,
  "rel_status": "none",
  "can_approve": false
}
```

**Error Response (403 Forbidden):**

```json
{ "Message": "Forbidden" }
```

---

### PUT `/authors/<author_id>/edit/`

**When:** When updating profile information.
**How:** Send JSON body with fields to update.
**Why:** Modify user info.
**Why Not:** Only owner may update.

**Request Body Example:**

```json
{
  "name": "Alice M. Johnson",
  "description": "Backend Developer",
  "github": "alice_dev",
  "profile_picture": "https://img.example.com/alice_new.jpg"
}
```

**Fields:**

| Field | Type | Example | Purpose |
| ----- | ---- | ------- | ------- |
| name  | string | "Alice M. Johnson" | Display name |
| description | string | "Backend Developer" | Profile bio  |
| github | string | "[https://github.com/alice_dev](https://github.com/alice_dev)" | GitHub URL   |
| profile_picture | string | URL | Avatar |

**Success Response:** 200 OK with updated profile JSON.
**Error Response:** 403 if unauthorized.
---

## Entries

### POST `/authors/<author_id>/entries/`

**When:** Creating a new entry.
**How:** Send JSON with content and metadata.
**Why:** Add content to your blog/feed.
**Why Not:** Auth required; content must match content_type.

**Request Body Examples:**
**Text Entry:**

```json
{
  "title": "My First Blog Post",
  "content": "Hello world!",
  "content_type": "text/markdown",
  "visibility": "PUBLIC"
}
```

**Image Entry:**

```json
{
  "title": "My Image Post",
  "content": "<base64_encoded_image>",
  "content_type": "image/png;base64",
  "visibility": "UNLISTED"
}
```

**Response:**

```json
{
  "id": "entry_1",
  "author": "user_1",
  "title": "My First Blog Post",
  "content": "Hello world!",
  "content_type": "text/markdown",
  "visibility": "PUBLIC",
  "share_token": "uuid-here",
  "created": "2025-10-19T18:10:00Z",
  "updated": "2025-10-19T18:10:00Z"
}
```

### GET `/authors/<author_id>/entries/`

**When:** Retrieve all entries for a user.
**Pagination:** Supports `?page=<number>&page_size=<number>`.

**Response Example:**

```json
[
  {
    "id": "entry_1",
    "title": "My First Blog Post",
    "content": "Hello world!",
    "visibility": "PUBLIC",
    "created": "2025-10-19T18:10:00Z"
  }
]
```

### GET/PUT/PATCH `/authors/<author_id>/entries/<entry_id>/`

**When:** View or update a specific entry.
**Errors:** 404 if entry not found, 403 if unauthorized.

### DELETE `/authors/<author_id>/entries/<entry_id>/delete/`

**When:** Remove an entry.
**Errors:** 404 if entry not found, 403 if unauthorized.

---

## Comments

### GET/POST `/authors/<author_id>/entries/<entry_id>/comments/`

**When:** List or add comments.
**Request Body Example (POST):**

```json
{
  "comment": "Great post!",
  "content_type": "text/plain"
}
```

**Response Example:**

```json
[
  {
    "id": "comment_1",
    "entry": "entry_1",
    "author": "user_2",
    "comment": "Great post!",
    "created": "2025-10-19T18:15:00Z"
  }
]
```

**Special Notes:** Supports pagination `?page=&page_size=`.

---

## Likes

### POST `/authors/<author_id>/entries/<entry_id>/likes`

**When:** To like or unlike a post.

**How:** Send a POST request with JWT authorization. This endpoint toggles the like status for the authenticated user.

**Why:** To allow users to express appreciation for an entry.

**Why Not:** Users can only like each entry once. Authentication required.

**Request Headers:**

```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Request Body Examples:**
**Like an Entry:**

```json
{
  "action": "like"
}
```

**Unlike an Entry:**

```json
{
  "action": "unlike"
}
```

**Request Fields:**

| Field  | Type   | Example | Purpose                               |
| ------ | ------ | ------- | ------------------------------------- |
| action | string | "like"  | Action to perform: "like" or "unlike" |

**Success Response:**

```json
{
  "likes_count": 5,
  "user_liked": true
}
```

**Error Examples:**

* 404: Entry not found
* 403: Unauthorized (not logged in)

---

### POST `/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes`

**When:** To like or unlike a comment.

**How:** Send a POST request with JWT authorization. Toggles like status for the comment.

**Why:** Enable users to react to comments.

**Why Not:** Users can only like a comment once. Authentication required.

**Request Headers:**

```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Request Body Examples:**
**Like a Comment:**

```json
{
  "action": "like"
}
```

**Unlike a Comment:**

```json
{
  "action": "unlike"
}
```

**Request Fields:**

| Field  | Type   | Example | Purpose                               |
| ------ | ------ | ------- | ------------------------------------- |
| action | string | "like"  | Action to perform: "like" or "unlike" |

**Success Response:**

```json
{
  "likes_count": 3,
  "user_liked": true
}
```

**Error Examples:**

* 404: Comment not found
* 403: Unauthorized