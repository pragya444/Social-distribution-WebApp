# API Endpoint Documentation

This documentation provides **comprehensive details for every API endpoint**, including when, how, and why to use them; multiple examples (success, minimal, and error); full JSON field tables with types, example values, and purposes; pagination notes; and special considerations.

---

## Base URL
```
http://127.0.0.1:8000/
```

## Authentication Endpoints

### GET/POST `/auth/register/`

**When to Use**: When a new user wants to create an account through the web interface  
**How to Use**:
- GET: Load the registration form
- POST: Submit form data with user credentials  
**Why Use**: To onboard new users with a traditional web form experience  
**Why Not Use**: For programmatic user creation (use JSON API if available)  

**Request (POST - Form Data)**:
```
username=alice
password=secure123
name=Alice
github=alicecodes
```

**Form Fields**:

| Field       | Type   | Example       | Purpose                             |
|-------------|--------|---------------|-------------------------------------|
| username    | string | "alice"       | Unique login identifier (required)  |
| password    | string | "secure123"   | Account password, min 8 chars (required) |
| name        | string | "Alice"       | Display name (required)             |
| github      | string | "alicecodes"  | GitHub username, auto-formatted to URL |

**Success Response**: 302 Redirect to `/authors/<user_id>/stream/` with JWT cookie  
**Error Response**: 400 Bad Request with HTML form showing validation errors  

**Special Notes**:
- Auto-prefixes GitHub usernames with `https://github.com/`
- Successful registration automatically logs in user and sets JWT cookie
- Uses traditional web form workflow, not JSON API

### GET/POST `/auth/login/`

**When to Use**: When existing users need to authenticate via web interface  
**How to Use**:
- GET: Load login form
- POST: Submit credentials as form data  
**Why Use**: For web-based authentication flow  
**Why Not Use**: For API token-based authentication  

**Request (POST - Form Data)**:
```
username=alice
password=secure123
```

**Form Fields**:

| Field    | Type   | Example       | Purpose                     |
|----------|--------|---------------|-----------------------------|
| username | string | "alice"       | User's login identifier     |
| password | string | "secure123"   | User's password             |

**Success Response**: 302 Redirect to user's stream with JWT cookie set  
**Error Response**: 400 Bad Request with login form showing error message  

**Special Notes**:
- Sets `jwt` cookie with 7-day expiration
- Uses HTTP-only cookies for security
- Redirects to user-specific stream page after login

### POST `/auth/logout/`

**When to Use**: When user wants to end their session  
**How to Use**: Send POST request 
**Why Use**: To securely clear authentication state  
**Why Not Use**: For partial session management  

**Request**: POST with CSRF token (included in form)  

**Success Response**: 302 Redirect to `/auth/login/`  

**Cookies Cleared**:
- `jwt` - Authentication token
- `sessionid` - Django session
- `csrftoken` - CSRF protection token  

**Special Notes**: Completely clears all authentication-related cookies

## User Profile Endpoints

### GET `/authors/<author_id>/`

**When to Use**: To view a user's public profile and entries  
**How to Use**: Send GET request (authentication required)  
**Why Use**: To see user details, bio, and their content  
**Why Not Use**: For editing profile information  

**URL Parameters**:

| Parameter  | Type   | Example     | Purpose                        |
|------------|--------|-------------|--------------------------------|
| author_id  | string | "user_123"  | Unique identifier for the author |

**Success Response (HTML)**: Rendered profile page with:
- User information
- List of user's entries
- Follow counts and relationship status  

**Success Response (JSON)**: Only when requested with `Accept: application/json`
```json
{
  "user": {
    "id": "user_123",
    "username": "alice",
    "name": "Alice",
    "description": "Software developer",
    "github": "https://github.com/alice",
    "profile_picture": "",
    "url": "http://127.0.0.1:8000/authors/user_123",
    "created": "2025-01-01T12:00:00Z"
  },
  "entries": [...],
  "posts_count": 5,
  "followers_count": 10,
  "following_count": 3,
  "rel_status": "none",
  "can_approve": false
}
```

**Error Responses**:
- 302 Redirect to login if not authenticated
- 403 Forbidden for JSON requests without authentication
- 404 Not Found if author doesn't exist  

**Special Notes**:
- Dual format endpoint (HTML and JSON)
- Shows different content to owner vs other users
- Includes relationship status for authenticated viewers

### GET/POST `/authors/<author_id>/edit/`

**When to Use**: When users want to update their profile information  
**How to Use**:
- GET: Load profile edit form
- POST: Submit updated profile data  
**Why Use**: For users to maintain their profile information  
**Why Not Use**: For creating new profiles or bulk updates  

**URL Parameters**:

| Parameter  | Type   | Example     | Purpose                        |
|------------|--------|-------------|--------------------------------|
| author_id  | string | "user_123"  | ID of profile being edited     |

**Request (POST - Form Data)**:
```
name=Alice+Johnson
description=Backend+developer
github=alice-dev
profile_picture=https://example.com/photo.jpg
```

**Form Fields**:

| Field           | Type   | Example                  | Purpose                        |
|-----------------|--------|--------------------------|--------------------------------|
| name            | string | "Alice Johnson"          | Display name (cannot be blank) |
| description     | string | "Backend developer"      | Profile biography              |
| github          | string | "alice-dev"              | GitHub username/URL            |
| profile_picture | string | "https://..."            | URL to profile image           |

**Success Response**: 302 Redirect to profile page  
**Error Response**: 400 Bad Request with form errors  

**Special Notes**:
- Owner-only access (403 if unauthorized)
- GitHub fields auto-formatted to full URLs
- Name field validation prevents blank values

## Entry Management Endpoints

### GET/POST `/authors/<author_id>/entries/new/`

**When to Use**: To create new blog entries or image posts via web form  
**How to Use**:
- GET: Load entry creation form
- POST: Submit form with entry content and metadata  
**Why Use**: For rich content creation with image upload support  
**Why Not Use**: For programmatic entry creation  

**URL Parameters**:

| Parameter  | Type   | Example     | Purpose                        |
|------------|--------|-------------|--------------------------------|
| author_id  | string | "user_123"  | Author creating the entry      |

**Request (POST - Multipart Form Data)**:
```
title=My_First_Post
content=Hello+world
contentType=text/markdown
visibility=PUBLIC
```

**Form Fields**:

| Field        | Type        | Example          | Purpose                        |
|--------------|-------------|------------------|--------------------------------|
| title        | string      | "My First Post"  | Entry title (required)         |
| content      | string/file | "Hello world"    | Text content or image file     |
| contentType  | string      | "text/markdown"  | Format of text content         |
| visibility   | string      | "PUBLIC"         | Who can see this entry         |
| as_image     | checkbox    | "on"             | Flag to treat upload as image   |
| image        | file        | [binary]         | Image file when as_image is checked |

**Visibility Options**:
- PUBLIC - Visible to everyone
- UNLISTED - Accessible with link
- FRIENDS - Only visible to mutual followers
- PRIVATE - Only visible to owner  

**Success Response**: 302 Redirect to author's stream  
**Error Response**: 400 Bad Request with form errors  

**Special Notes**:
- Supports both text and image entries
- Images are validated and converted to base64
- Auto-detects markdown content
- Owner-only access (403 if unauthorized)

### GET/POST `/authors/<author_id>/entries/`

**When to Use**: To programmatically list or create entries via JSON API  
**How to Use**:
- GET: Retrieve entries as JSON
- POST: Create new entry with JSON payload  
**Why Use**: For API clients and programmatic access  
**Why Not Use**: For web form-based entry creation  

**Request (POST - JSON)**:
```json
{
  "title": "My API Post",
  "content": "Hello from API",
  "contentType": "text/markdown",
  "visibility": "PUBLIC"
}
```

**JSON Request Fields**:

| Field       | Type   | Example          | Purpose                        |
|-------------|--------|------------------|--------------------------------|
| title       | string | "My API Post"    | Entry title                    |
| content     | string | "Hello world"    | Entry content                  |
| contentType | string | "text/markdown"  | Content format                 |
| visibility  | string | "PUBLIC"         | Access level                   |

**Response (GET - JSON)**:
```json
{
  "type": "entries",
  "count": 2,
  "src": [
    {
      "type": "entry",
      "title": "My First Post",
      "id": "http://127.0.0.1:8000/authors/user_123/entries/entry_456",
      "contentType": "text/markdown",
      "content": "Hello world",
      "author": {
        "type": "author",
        "id": "http://127.0.0.1:8000/authors/user_123",
        "displayName": "alice",
        "github": "https://github.com/alice",
        "profileImage": ""
      },
      "published": "2025-10-19T18:10:00Z",
      "visibility": "PUBLIC"
    }
  ]
}
```

**Special Notes**:
- JSON API endpoint (different from web form endpoint)
- Owner-only creation (403 if unauthorized)
- Returns entries in ActivityPub-like format

### GET/PUT/PATCH `/authors/<author_id>/entries/<entry_id>/`

**When to Use**: To retrieve or update specific entries via JSON API  
**How to Use**:
- GET: Fetch single entry
- PUT/PATCH: Update entry fields  
**Why Use**: For programmatic entry management  
**Why Not Use**: For web-based editing  

**URL Parameters**:

| Parameter  | Type   | Example     | Purpose                        |
|------------|--------|-------------|--------------------------------|
| author_id  | string | "user_123"  | Entry author                   |
| entry_id   | string | "entry_456" | Specific entry to access       |

**Request (PUT/PATCH - JSON)**:
```json
{
  "title": "Updated Title",
  "content": "Updated content",
  "visibility": "FRIENDS"
}
```

**Success Response**: 200 OK with updated entry JSON  
**Error Responses**:
- 404 Not Found if entry doesn't exist
- 403 Forbidden if not owner
- 405 Method Not Allowed for invalid methods  

**Special Notes**:
- Supports partial updates with PATCH
- Updates `updated` timestamp automatically
- Owner-only modifications

## Comment Endpoints

### GET/POST `/authors/<author_id>/entries/<entry_id>/comments`

**When to Use**: To view or add comments on an entry  
**How to Use**:
- GET: List comments with pagination
- POST: Add new comment as JSON  
**Why Use**: For entry discussion and engagement  
**Why Not Use**: For modifying existing comments  

**URL Parameters**:

| Parameter  | Type   | Example     | Purpose                        |
|------------|--------|-------------|--------------------------------|
| author_id  | string | "user_123"  | Entry author                   |
| entry_id   | string | "entry_456" | Entry being commented on       |

**Query Parameters (GET)**:

| Parameter | Type    | Example | Purpose                        |
|-----------|---------|---------|--------------------------------|
| page      | integer | 1       | Page number for pagination     |
| size      | integer | 10      | Comments per page              |

**Request (POST - JSON)**:
```json
{
  "comment": "Great post!",
  "contentType": "text/plain"
}
```

**JSON Request Fields**:

| Field       | Type   | Example        | Purpose                        |
|-------------|--------|----------------|--------------------------------|
| comment     | string | "Great post!"  | Comment text (required)        |
| contentType | string | "text/plain"   | Content format                 |

**Response (GET - JSON)**:
```json
{
  "type": "comments",
  "id": "/api/authors/user_123/entries/entry_456/comments",
  "page_number": 1,
  "size": 10,
  "count": 5,
  "src": [
    {
      "type": "comment",
      "id": "/api/authors/user_123/entries/entry_456/comments/comment_789",
      "comment": "Great post!",
      "contentType": "text/plain",
      "published": "2025-10-19T18:15:00Z",
      "author": {
        "type": "author",
        "id": "http://127.0.0.1:8000/authors/user_456",
        "displayName": "bob",
        "github": "https://github.com/bob",
        "profileImage": ""
      }
    }
  ]
}
```

**Special Notes**:
- Pagination supported via `page` and `size` query parameters
- Authentication required for posting comments
- Visibility rules apply (can't comment on invisible entries)

## Like Endpoints

### GET/POST/DELETE `/authors/<author_id>/entries/<entry_id>/likes`

**When to Use**: To view, add, or remove likes on entries  
**How to Use**:
- GET: See who liked the entry
- POST: Like the entry
- DELETE: Remove like  
**Why Use**: For user engagement and feedback  
**Why Not Use**: For bulk like operations  

**URL Parameters**:

| Parameter  | Type   | Example     | Purpose                        |
|------------|--------|-------------|--------------------------------|
| author_id  | string | "user_123"  | Entry author                   |
| entry_id   | string | "entry_456" | Entry being liked              |

**Request Body (POST/DELETE)**: Empty or any value (action determined by method)  

**Response (GET - JSON)**:
```json
{
  "type": "likes",
  "count": 3,
  "liked": true,
  "src": [
    {
      "type": "author",
      "id": "http://127.0.0.1:8000/authors/user_456",
      "displayName": "bob",
      "web": "/authors/user_456"
    }
  ]
}
```

**Response (POST - JSON)**:
```json
{
  "ok": true,
  "liked": true,
  "count": 4
}
```

**Special Notes**:
- Idempotent operations (multiple POSTs = single like)
- `liked` field indicates current user's like status
- Authentication required for POST/DELETE

### GET/POST/DELETE `/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes`

**When to Use**: To manage likes on comments  
**How to Use**: Same pattern as entry likes  
**Why Use**: For comment-level engagement  
**Why Not Use**: For entry-level likes  
**Note**: This API Endpoint is still not done. Under construction

**URL Parameters**:

| Parameter   | Type   | Example       | Purpose                        |
|-------------|--------|---------------|--------------------------------|
| author_id   | string | "user_123"    | Entry author                   |
| entry_id    | string | "entry_456"   | Parent entry                   |
| comment_id  | string | "comment_789" | Comment being liked            |

**Response Format**: Same structure as entry likes  

**Special Notes**:
- Separate endpoint from entry likes
- Same idempotent behavior
- Authentication required for modifications

## Special Endpoints

### GET `/authors/<author_id>/stream/`

**When to Use**: To view personalized content feed  
**How to Use**: GET with optional tab parameter  
**Why Use**: For aggregated content viewing  
**Why Not Use**: For specific entry management  

**Query Parameters**:

| Parameter | Type   | Example       | Purpose                        |
|-----------|--------|---------------|--------------------------------|
| tab       | string | "following"   | Feed content filter            |

**Tab Options**:
- `all` - All visible content (default)
- `following` - Content from followed users
- `friends` - Friends-only content
- `private` - User's private entries  

**Response**: HTML page with filtered entries  

**Special Notes**:
- Complex visibility logic
- Combines multiple content sources
- Personalized based on follow relationships

### GET `/api/authors/<author_id>/entries/<entry_id>/image/`

**When to Use**: To retrieve image entries as binary data  
**How to Use**: GET request to image endpoint  
**Why Use**: For serving uploaded images  
**Why Not Use**: For text content retrieval  

**Response**: Binary image data with appropriate Content-Type  

**Special Notes**:
- Only for entries with image content types
- Returns raw binary, not base64
- Automatic content type detection

## Pagination

**Supported Endpoints**:
- GET /authors/<author_id>/entries/<entry_id>/comments  

**Usage**:
```
GET /authors/user_123/entries/entry_456/comments?page=2&size=20
```

**Response Fields**:

| Field        | Type    | Example | Purpose                        |
|--------------|---------|---------|--------------------------------|
| page_number  | integer | 2       | Current page (1-based)         |
| size         | integer | 20      | Items per page                 |
| count        | integer | 45      | Total items available          |
| src          | array   | [...]   | Current page items             |

**Default Values**: `page=1`, `size=10`

## Authentication Method

**Primary Method**: JWT tokens in HTTP-only cookies
- Token automatically set during login/registration
- Automatically included in requests by browser
- 7-day expiration
- No manual token management required for web clients  

**For API Clients**: Use the JSON endpoints that don't rely on cookie auth

## Error Handling

**Common HTTP Status Codes**:
- 302 Redirect - Authentication required or success action
- 400 Bad Request - Validation errors
- 403 Forbidden - Authorization failure
- 404 Not Found - Resource doesn't exist
- 405 Method Not Allowed - Invalid HTTP method  
