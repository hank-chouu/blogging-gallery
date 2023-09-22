from bs4 import BeautifulSoup
from math import ceil
from flask import abort, Request
from flask_login import current_user
from application.config import ENV
from application.services.mongo import my_database, MyDatabase
from application.utils.common import uid_generator, get_today

###################################################################

# create new post

###################################################################


def process_tags(tag_string: str):

    if tag_string == "":
        return []
    return [tag.strip().replace(" ", "-") for tag in tag_string.split(",")]


class NewPostSetup:
    def __init__(
        self,
        request: Request,
        post_uid_generator: uid_generator,
        db_handler: MyDatabase,
        author_name: str,
    ) -> None:

        self._request = request
        self._post_uid = post_uid_generator.generate_post_uid()
        self._db_handler = db_handler
        self._author_name = author_name

    def _form_validatd(self):
        return True

    def _create_post_info(self) -> dict:

        new_post_info = {
            "title": self._request.form.get("title"),
            "subtitle": self._request.form.get("subtitle"),
            "author": self._author_name,
            "post_uid": self._post_uid,
            "tags": process_tags(self._request.form.get("tags")),
            "banner_url": self._request.form.get("banner_url"),
            "created_at": get_today(env=ENV),
            "last_updated": get_today(env=ENV),
            "archived": False,
            "featured": False,
        }
        return new_post_info

    def _create_post_content(self) -> dict:

        new_post_content = {
            "post_uid": self._post_uid,
            "author": self._author_name,
            "content": self._request.form.get("content"),
        }
        return new_post_content

    def create_post(self):

        new_post_info = self._create_post_info()
        new_post_content = self._create_post_content()

        self._db_handler.post_info.insert_one(new_post_info)
        self._db_handler.post_content.insert_one(new_post_content)

        return self._post_uid


def create_post(request):

    new_post_setup = NewPostSetup(
        request=request,
        post_uid_generator=uid_generator,
        db_handler=my_database,
        author_name=current_user.username,
    )
    return new_post_setup.create_post()


###################################################################

# updating a post

###################################################################


class PostUpdateSetup:
    def __init__(self, post_uid: str, request: Request, db_handler=MyDatabase) -> None:

        self._post_uid = post_uid
        self._request = request
        self._db_handler = db_handler

    def _updated_post_info(self) -> dict:

        updated_post_info = {
            "title": self._request.form.get("title"),
            "subtitle": self._request.form.get("subtitle"),
            "tags": process_tags(self._request.form.get("tags")),
            "banner_url": self._request.form.get("banner_url"),
            "last_updated": get_today(env=ENV),
        }
        return updated_post_info

    def _updated_post_content(self) -> dict:

        updated_post_content = {"content": self._request.form.get("content")}
        return updated_post_content

    def update_post(self):

        updated_post_info = self._updated_post_info()
        updated_post_content = self._updated_post_content()

        self._db_handler.post_info.simple_update(
            filter={"post_uid": self._post_uid}, update=updated_post_info
        )
        self._db_handler.post_content.simple_update(
            filter={"post_uid": self._post_uid}, update=updated_post_content
        )


def update_post(post_uid, request):

    post_update_setup = PostUpdateSetup(
        post_uid=post_uid, request=request, db_handler=my_database
    )
    post_update_setup.update_post()

###################################################################

# formatter for posts that are saved as markdown

###################################################################


class HTMLFormatter:
    def __init__(self, html):

        self.__soup = BeautifulSoup(html, "html.parser")

    def add_padding(self):

        # add padding for all first level tags, except figure and img
        tags = self.__soup.find_all(
            lambda tag: tag.name not in ["figure", "img"], recursive=False
        )
        for tag in tags:
            current_style = tag.get("style", "")
            new_style = f"{current_style} padding-top: 10px; padding-bottom: 10px; "
            tag["style"] = new_style

        return self

    def change_heading_font(self):

        # Modify the style attribute for each heading tag
        headings = self.__soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

        # Modify the style attribute for each heading tag
        for heading in headings:
            current_style = heading.get("style", "")
            new_style = f"{current_style} font-family: 'Ubuntu', 'Arial', sans-serif;;"
            heading["style"] = new_style

        return self

    def modify_figure(self, max_width="90%"):

        # center image and modify size
        imgs = self.__soup.find_all(["img"])
        for img in imgs:
            current_style = img.get("style", "")
            new_style = f"{current_style} display: block; margin: 0 auto; max-width: {max_width}; min-width: 30% ;height: auto;"
            img["style"] = new_style

        # center caption
        captions = self.__soup.find_all(["figcaption"])
        for caption in captions:
            current_style = caption.get("style", "")
            new_style = f"{current_style} text-align: center"
            caption["style"] = new_style

        return self

    def to_string(self):

        return str(self.__soup)


def html_to_blogpost(html):

    formatter = HTMLFormatter(html)
    blogpost = formatter.add_padding().change_heading_font().modify_figure().to_string()

    return blogpost

def html_to_about(html):

    formatter = HTMLFormatter(html)
    about = formatter.add_padding().modify_figure(max_width="50%").to_string()

    return about

###################################################################

# counting tags in posts

###################################################################


class All_Tags:
    def __init__(self, db_handler: MyDatabase) -> None:

        self._db_handler = db_handler

    def from_user(self, username):

        result = self._db_handler.post_info.find(
            {"author": username, "archived": False}
        )
        tags_dict = {}
        for post in result:
            post_tags = post["tags"]
            for tag in post_tags:
                if tag not in tags_dict:
                    tags_dict[tag] = 1
                else:
                    tags_dict[tag] += 1

        sorted_tags_key = sorted(tags_dict, key=tags_dict.get, reverse=True)
        sorted_tags = {}
        for key in sorted_tags_key:
            sorted_tags[key] = tags_dict[key]

        return sorted_tags


all_tags = All_Tags(db_handler=my_database)

###################################################################

# blogpost pagination (also apply for backstage)

###################################################################


class Paging:
    def __init__(self, db_handler: MyDatabase) -> None:

        self._db_handler = db_handler
        self._has_setup = False
        self._allow_previous_page = None
        self._allow_next_page = None
        self._current_page = None

    def setup(self, username, current_page, posts_per_page):

        self._has_setup = True
        self._allow_previous_page = False
        self._allow_next_page = False
        self._current_page = current_page

        # set up for pagination
        num_not_archieved = self._db_handler.post_info.count_documents(
            {"author": username, "archived": False}
        )
        if num_not_archieved == 0:
            max_page = 1
        else:
            max_page = ceil(num_not_archieved / posts_per_page)

        if current_page > max_page:
            # not a legal page number
            abort(404)

        if current_page * posts_per_page < num_not_archieved:
            self._allow_previous_page = True

        if current_page > 1:
            self._allow_next_page = True

    @property
    def is_previous_page_allowed(self):

        if not self._has_setup:
            raise AttributeError("pagination has not setup yet.")
        return self._allow_previous_page

    @property
    def is_next_page_allowed(self):

        if not self._has_setup:
            raise AttributeError("pagination has not setup yet.")
        return self._allow_next_page

    @property
    def current_page(self):

        if not self._has_setup:
            raise AttributeError("pagination has not setup yet.")
        return self._current_page


paging = Paging(db_handler=my_database)


###################################################################

# post utilities

###################################################################


class PostUtils:
    def __init__(self, db_handler: MyDatabase):

        self._db_handler = db_handler

    def find_featured_posts_info(self, username: str):

        result = (
            self._db_handler.post_info
            .find({"author": username, "featured": True, "archived": False})
            .sort("created_at", -1)
            .limit(10)
            .as_list()
        )
        return result

    def find_all_posts_info(self, username: str):

        result = (
            self._db_handler.post_info.find({"author": username, "archived": False})
            .sort("created_at", -1)
            .as_list()
        )
        return result

    def find_all_archived_posts_info(self, username: str):

        result = (
            self._db_handler.post_info
            .find({"author": username, "archived": True})
            .sort("created_at", -1)
            .as_list()
        )
        return result

    def find_posts_with_pagination(
        self, username: str, page_number: int, posts_per_page: int
    ):
        
        if page_number == 1:
            result = (
                self._db_handler.post_info
                .find({"author": username, "archived": False})
                .sort("created_at", -1)
                .limit(posts_per_page)
                .as_list()
            )

        elif page_number > 1:
            result = (
                self._db_handler.post_info
                .find({"author": username, "archived": False})
                .sort("created_at", -1)
                .skip((page_number - 1) * posts_per_page)
                .limit(posts_per_page)
                .as_list()
            )

        return result

    def get_full_post(self, post_uid: str):

        target_post = self._db_handler.post_info.find_one({"post_uid": post_uid})
        target_post_content = self._db_handler.post_content.find_one(
            {"post_uid": post_uid}
        )["content"]
        target_post["content"] = target_post_content

        return target_post


post_utils = PostUtils(db_handler=my_database)