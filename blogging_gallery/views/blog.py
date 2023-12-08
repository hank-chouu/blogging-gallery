from urllib.parse import unquote

import bcrypt
import readtime
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_user
from markdown import Markdown

from blogging_gallery.config import ENV
from blogging_gallery.services.log import my_logger, return_client_ip
from blogging_gallery.services.mongo import my_database
from blogging_gallery.utils.comments import comment_utils, create_comment
from blogging_gallery.utils.metrics import admin_metrics, lifetime_metrics, timely_metrics
from blogging_gallery.utils.posts import (
    all_tags,
    html_to_about,
    html_to_blogpost,
    paging,
    post_utils,
)
from blogging_gallery.utils.users import User, create_user

blog = Blueprint("blog", __name__, template_folder="../templates/blog/")


@blog.route("/", methods=["GET"])
def landing_page():
    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)
    admin_metrics.page_viewed(request, page="landing_page")

    ###################################################################

    # return page content

    ###################################################################

    return render_template("landing_page.html")


@blog.route("/login", methods=["GET"])
def login_get():
    ###################################################################

    # early returns

    ###################################################################

    if current_user.is_authenticated:
        flash("You are already logged in.")
        my_logger.debug(
            f"{return_client_ip(request, ENV)} - Attempt to duplicate logging from user {current_user.username}."
        )
        return redirect(url_for("backstage.overview"))

    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return render_template("login.html")


@blog.route("/login", methods=["POST"])
def login_post():
    ###################################################################

    # early returns

    ###################################################################

    login_form = request.form.to_dict()
    if not my_database.user_login.exists("email", login_form["email"]):
        flash("Account not found. Please try again.", category="error")
        my_logger.user.login_failed(
            msg=f"email {login_form['email']} not found", request=request
        )
        return render_template("login.html")

    # check pw
    user_creds = my_database.user_login.find_one({"email": login_form["email"]})
    encoded_input_pw = login_form["password"].encode("utf8")
    encoded_valid_user_pw = user_creds["password"].encode("utf8")

    if not bcrypt.checkpw(encoded_input_pw, encoded_valid_user_pw):
        flash("Invalid password. Please try again.", category="error")
        my_logger.user.login_failed(
            msg=f"invalid password with email {login_form['email']}", request=request
        )
        return render_template("login.html")

    ###################################################################

    # main actions

    ###################################################################

    user = User(user_creds)
    login_user(user)
    my_logger.user.login_succeeded(username=user_creds["username"], request=request)
    flash("Login Succeeded.", category="success")

    ###################################################################

    # return page content

    ###################################################################

    return redirect(url_for("backstage.backstage_root"))


@blog.route("/register", methods=["GET"])
def register_get():
    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return render_template("register.html")


@blog.route("/register", methods=["POST"])
def register_post():
    ###################################################################

    # main actions

    ###################################################################

    username = create_user(request=request)
    my_logger.user.registration_succeeded(username=username, request=request)
    flash("Registration succeeded.", category="success")

    ###################################################################

    # return page content

    ###################################################################

    return redirect(url_for("blog.login_get"))


@blog.route("/@<username>", methods=["GET"])
def home(username):
    ###################################################################

    # early returns

    ###################################################################

    if not my_database.user_info.exists("username", username):
        my_logger.invalid_username(username=username, request=request)
        abort(404)

    ###################################################################

    # main actions

    ###################################################################

    user = my_database.user_info.find_one({"username": username})
    featured_posts = post_utils.find_featured_posts_info(username)
    for post in featured_posts:
        post["created_at"] = post["created_at"].strftime("%Y-%m-%d")

    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)
    lifetime_metrics.page_viewed(request=request)
    timely_metrics.page_viewed(request=request)
    timely_metrics.index_page_viewed(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return render_template("home.html", user=user, posts=featured_posts)


@blog.route("/@<username>/tags", methods=["GET"])
def tag(username):
    ###################################################################

    # early returns

    ###################################################################

    if not my_database.user_info.exists("username", username):
        my_logger.invalid_username(username=username, request=request)
        abort(404)

    # if no tag specified, show blog page
    tag_url_encoded = request.args.get("tag", default=None, type=str)
    if tag_url_encoded is None:
        return redirect(url_for("blog.blog_page", username=username))

    # abort for unknown tag
    tag = unquote(tag_url_encoded)
    tags_found = all_tags.from_user(username)
    if tag not in tags_found.keys():
        abort(404)

    ###################################################################

    # main actions

    ###################################################################

    user = my_database.user_info.find_one({"username": username})
    posts = post_utils.find_all_posts_info(username)

    posts_with_desired_tag = []
    for post in posts:
        if tag in post["tags"]:
            post["created_at"] = post["created_at"].strftime("%Y-%m-%d")
            posts_with_desired_tag.append(post)

    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)
    lifetime_metrics.page_viewed(request=request)
    timely_metrics.page_viewed(request=request)
    timely_metrics.index_page_viewed(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return render_template("tag.html", user=user, posts=posts_with_desired_tag, tag=tag)


@blog.route("/@<username>/posts/<post_uid>", methods=["GET", "POST"])
def post(username, post_uid):
    ###################################################################

    # early return for invalid inputs

    ###################################################################

    if not my_database.user_info.exists("username", username):
        my_logger.invalid_username(username=username, request=request)
        abort(404)
    if not my_database.post_info.exists("post_uid", post_uid):
        my_logger.invalid_post_uid(username=username, post_uid=post_uid, request=request)
        abort(404)

    author = my_database.post_info.find_one({"post_uid": post_uid})["author"]
    if username != author:
        my_logger.invalid_author_for_post(
            username=username, post_uid=post_uid, request=request
        )
        abort(404)

    ###################################################################

    # main actions

    ###################################################################

    author_info = my_database.user_info.find_one({"username": username})
    target_post = post_utils.get_full_post(post_uid)

    md = Markdown(extensions=["markdown_captions", "fenced_code", "footnotes"])
    target_post["content"] = md.convert(target_post["content"])
    target_post["content"] = html_to_blogpost(target_post["content"])
    target_post["last_updated"] = target_post["last_updated"].strftime("%Y-%m-%d")
    target_post["readtime"] = str(readtime.of_html(target_post["content"]))

    # add comments
    # this section should be placed before finding comments to show on the postu'1 min read'
    if request.method == "POST":
        create_comment(post_uid, request)
        flash("Comment published!", category="success")

    # find comments
    # oldest to newest comment
    comments = comment_utils.find_comments_by_post_uid(post_uid)
    for comment in comments:
        comment["created_at"] = comment["created_at"].strftime("%Y-%m-%d %H:%M:%S")

    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)
    lifetime_metrics.page_viewed(request=request)
    lifetime_metrics.post_viewed(request=request)
    timely_metrics.page_viewed(request=request)
    timely_metrics.post_viewed(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return render_template(
        "post.html", user=author_info, post=target_post, comments=comments
    )


@blog.route("/readcount-increment", methods=["GET"])
def readcount_increment():
    ###################################################################

    # logging / metrics

    ###################################################################

    lifetime_metrics.post_read(request=request)
    timely_metrics.post_read(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return "OK"


@blog.route("/@<username>/about", methods=["GET"])
def about(username):
    ###################################################################

    # early return for invalid inputs

    ###################################################################

    if not my_database.user_info.exists("username", username):
        my_logger.invalid_username(username=username, request=request)
        abort(404)

    ###################################################################

    # main actions

    ###################################################################

    user = my_database.user_info.find_one({"username": username})
    user_about = my_database.user_about.find_one({"username": username})["about"]

    md = Markdown(extensions=["markdown_captions", "fenced_code"])
    about = md.convert(user_about)
    about = html_to_about(about)

    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)
    lifetime_metrics.page_viewed(request=request)
    lifetime_metrics.index_page_viewed(request=request)
    timely_metrics.page_viewed(request=request)
    timely_metrics.index_page_viewed(request=request)
    my_database.user_about.make_increments(
        filter={"username": username},
        increments={"about_views": 1},
        # upsert=True
    )

    ###################################################################

    # return page content

    ###################################################################

    return render_template("about.html", user=user, about=about)


@blog.route("/@<username>/blog", methods=["GET"])
def blog_page(username):
    ###################################################################

    # early returns

    ###################################################################

    if not my_database.user_info.exists("username", username):
        my_logger.invalid_username(username=username, request=request)
        abort(404)

    ###################################################################

    # main actions

    ###################################################################

    user = my_database.user_info.find_one({"username": username})
    current_page = request.args.get("page", default=1, type=int)
    POSTS_EACH_PAGE = 10

    # create a tag dict
    tags_dict = all_tags.from_user(username)

    # set up pagination
    pagination = paging.setup(username, current_page, POSTS_EACH_PAGE)

    # skip and limit posts with given page
    posts = post_utils.find_posts_with_pagination(
        username=username, page_number=current_page, posts_per_page=POSTS_EACH_PAGE
    )
    for post in posts:
        post["created_at"] = post["created_at"].strftime("%Y-%m-%d")

    ###################################################################

    # logging / metrics

    ###################################################################

    my_logger.page_viewed(request=request)
    lifetime_metrics.page_viewed(request=request)
    lifetime_metrics.index_page_viewed(request=request)
    timely_metrics.page_viewed(request=request)
    timely_metrics.index_page_viewed(request=request)

    ###################################################################

    # return page content

    ###################################################################

    return render_template(
        "blog.html", user=user, posts=posts, tags=tags_dict, pagination=pagination
    )


@blog.route("@<username>/social-links", methods=["GET"])
def social_link_endpoint(username):
    ###################################################################

    # main actions

    ###################################################################

    user = my_database.user_info.find_one({"username": username})
    social_links = user["social_links"]
    link_idx = request.args.get("idx", type=int)
    target_url = social_links[link_idx - 1]["url"]
    if not target_url.startswith("https://"):
        target_url = "https://" + target_url

    ###################################################################

    # logging / metrics

    ###################################################################

    client_ip = return_client_ip(request, ENV)
    my_logger.debug(f"{client_ip} - redirect to social link {target_url}")
    timely_metrics.social_link_fired(request)

    ###################################################################

    # return page content

    ###################################################################

    return redirect(target_url)


@blog.route("/@<username>/get-profile-pic", methods=["GET"])
def profile_pic_endpoint(username):
    user = my_database.user_info.find_one({"username": username})

    if user["profile_img_url"]:
        profile_img_url = user["profile_img_url"]
    else:
        profile_img_url = "/static/img/default-profile.png"

    return jsonify({"imageUrl": profile_img_url})


@blog.route("/error", methods=["GET"])
def error_simulator():
    raise Exception("this is a simulation error.")